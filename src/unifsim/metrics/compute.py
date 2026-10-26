"""Metrics computed from the trace only (same definitions and names as shrimp).

Per job, its execution pieces sorted by time (contiguous pieces on the same
processor are already merged in the trace):
  - preemption : between two consecutive pieces, a gap or a processor change
                 (the end of the job is not a preemption);
  - migration  : a piece starts on a processor different from the previous one.
Local = between two pieces inside the same TL-plane (pieces are cut at plane
boundaries first); boundary = total - local. Only for schedulers that record
TL-planes; None otherwise.
Task migrations: processor changes over the pieces of all jobs of a task, in
time order; boundary task migrations = task migrations - job migrations.
Response time ratio of a completed job: (completion - release) / D.
  - *_response_time_ratio          : avg / max / min over all completed jobs
  - *_response_time_ratio_per_task : mean of each task over its completed jobs,
                                     then avg / max / min over the tasks
(shrimp: core/Simulator.py log_results, core/Job.py, core/Task.py)
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field, fields
from fractions import Fraction

COUNTERS = (
    "local_job_preemptions", "local_job_migrations",
    "boundary_job_preemptions", "boundary_job_migrations",
    "total_job_preemptions", "total_job_migrations",
    "total_task_migrations", "total_boundary_task_migrations",
)


@dataclass
class Metrics:
    scheduler: str
    n: int
    m: int
    horizon: Fraction
    n_jobs_released: int
    n_jobs_completed: int

    local_job_preemptions: int | None
    local_job_migrations: int | None
    boundary_job_preemptions: int | None
    boundary_job_migrations: int | None
    total_job_preemptions: int
    total_job_migrations: int
    total_task_migrations: int
    total_boundary_task_migrations: int

    avg_response_time_ratio: Fraction | None
    worst_response_time_ratio: Fraction | None
    best_response_time_ratio: Fraction | None
    avg_response_time_ratio_per_task: Fraction | None
    worst_response_time_ratio_per_task: Fraction | None
    best_response_time_ratio_per_task: Fraction | None

    # detail behind the numbers
    per_job: dict = field(default_factory=dict, repr=False)            # job -> (preemptions, migrations)
    per_plane_preemptions: list = field(default_factory=list, repr=False)  # [(t0, t1, local preemptions)]

    def per_job_value(self, name: str):
        """Counter divided by the number of jobs released in the horizon."""
        v = getattr(self, name)
        return None if v is None else Fraction(v, self.n_jobs_released)

    def as_row(self) -> dict:
        """Flat row with the shrimp column names (floats), for CSV export."""
        row = {}
        for f in fields(self):
            if f.name in ("per_job", "per_plane_preemptions"):
                continue
            v = getattr(self, f.name)
            row[f.name] = float(v) if isinstance(v, Fraction) else v
        for c in COUNTERS:
            v = self.per_job_value(c)
            row[f"{c}_per_job"] = None if v is None else float(v)
        return row

    def report(self) -> str:
        def num(v):
            return "-" if v is None else str(v)

        def pj(name):
            v = self.per_job_value(name)
            return "-" if v is None else f"{float(v):.3f}"

        def r(v):
            return "-" if v is None else f"{float(v):.4f}"

        lines = [
            f"=== {self.scheduler} | n={self.n} m={self.m} H={self.horizon} | "
            f"jobs released={self.n_jobs_released} completed={self.n_jobs_completed} ===",
            f"{'':22}{'local':>8}{'boundary':>10}{'total':>8}{'per job':>10}",
            f"{'job preemptions':22}{num(self.local_job_preemptions):>8}{num(self.boundary_job_preemptions):>10}"
            f"{self.total_job_preemptions:>8}{pj('total_job_preemptions'):>10}",
            f"{'job migrations':22}{num(self.local_job_migrations):>8}{num(self.boundary_job_migrations):>10}"
            f"{self.total_job_migrations:>8}{pj('total_job_migrations'):>10}",
            f"{'task migrations':22}{'-':>8}{self.total_boundary_task_migrations:>10}"
            f"{self.total_task_migrations:>8}{pj('total_task_migrations'):>10}",
            f"{'R/D over jobs':22}avg {r(self.avg_response_time_ratio)}  worst {r(self.worst_response_time_ratio)}"
            f"  best {r(self.best_response_time_ratio)}",
            f"{'R/D over tasks':22}avg {r(self.avg_response_time_ratio_per_task)}  "
            f"worst {r(self.worst_response_time_ratio_per_task)}  best {r(self.best_response_time_ratio_per_task)}",
        ]
        return "\n".join(lines)


def _events(pieces):
    """(preemptions, migrations) between consecutive pieces (start, end, proc)."""
    pre = mig = 0
    for (s0, e0, p0), (s1, e1, p1) in zip(pieces, pieces[1:]):
        if e0 < s1 or p0 != p1:
            pre += 1
        if p1 != p0:
            mig += 1
    return pre, mig


def _cut(pieces, bounds):
    """Cut pieces at the plane boundaries; returns [(plane index, start, end, proc)]."""
    out = []
    for s, e, p in pieces:
        i = bisect_right(bounds, s) - 1
        while s < e:
            b = bounds[i + 1] if i + 1 < len(bounds) else e
            end = min(e, b)
            out.append((i, s, end, p))
            s, i = end, i + 1
    return out


def compute_metrics(system, trace) -> Metrics:
    speeds = system.platform.speeds
    H = Fraction(trace.horizon)

    by_job = defaultdict(list)
    for s in trace.segments:
        by_job[s.job].append((s.start, s.end, s.proc))
    for v in by_job.values():
        v.sort()

    # --- job preemptions / migrations, total
    per_job = {j: _events(p) for j, p in by_job.items()}
    tot_pre = sum(a for a, _ in per_job.values())
    tot_mig = sum(b for _, b in per_job.values())

    # --- local / boundary (TL-plane schedulers only)
    loc_pre = loc_mig = None
    per_plane = []
    if trace.planes:
        bounds = sorted({p.t0 for p in trace.planes} | {p.t1 for p in trace.planes})
        plane_pre = defaultdict(int)
        loc_pre = loc_mig = 0
        for pieces in by_job.values():
            cut = _cut(pieces, bounds)
            for (i0, s0, e0, p0), (i1, s1, e1, p1) in zip(cut, cut[1:]):
                if i0 != i1:
                    continue
                if e0 < s1 or p0 != p1:
                    loc_pre += 1
                    plane_pre[i0] += 1
                if p1 != p0:
                    loc_mig += 1
        per_plane = [(bounds[i], bounds[i + 1], plane_pre[i]) for i in range(len(bounds) - 1)]

    # --- task migrations
    by_task = defaultdict(list)
    for j, pieces in by_job.items():
        by_task[j.task_id].extend(pieces)
    task_mig = 0
    for pieces in by_task.values():
        pieces.sort()
        task_mig += sum(1 for a, b in zip(pieces, pieces[1:]) if a[2] != b[2])

    # --- response times (completed jobs)
    released = system.jobs(H)
    ratios, per_task = [], defaultdict(list)
    n_completed = 0
    for j in released:
        pieces = by_job.get(j, [])
        work = sum(((e - s) * speeds[p] for s, e, p in pieces), Fraction(0))
        if pieces and work == j.C:
            n_completed += 1
            ratio = (pieces[-1][1] - j.release) / system.task(j.task_id).D
            ratios.append(ratio)
            per_task[j.task_id].append(ratio)
    task_means = [sum(v) / len(v) for v in per_task.values()]

    def agg(values):
        if not values:
            return None, None, None
        return sum(values) / len(values), max(values), min(values)

    avg, worst, best = agg(ratios)
    t_avg, t_worst, t_best = agg(task_means)

    return Metrics(
        scheduler=trace.meta.get("scheduler", "?"),
        n=system.n, m=system.platform.m, horizon=H,
        n_jobs_released=len(released), n_jobs_completed=n_completed,
        local_job_preemptions=loc_pre, local_job_migrations=loc_mig,
        boundary_job_preemptions=None if loc_pre is None else tot_pre - loc_pre,
        boundary_job_migrations=None if loc_mig is None else tot_mig - loc_mig,
        total_job_preemptions=tot_pre, total_job_migrations=tot_mig,
        total_task_migrations=task_mig, total_boundary_task_migrations=task_mig - tot_mig,
        avg_response_time_ratio=avg, worst_response_time_ratio=worst, best_response_time_ratio=best,
        avg_response_time_ratio_per_task=t_avg, worst_response_time_ratio_per_task=t_worst,
        best_response_time_ratio_per_task=t_best,
        per_job=per_job, per_plane_preemptions=per_plane,
    )
