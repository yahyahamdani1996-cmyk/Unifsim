"""DP: base class of all deadline-partitioned (TL-plane) schedulers.

It implements the Scheduler interface once:
  - TL-plane boundaries = all deadlines in (0, H], plus 0 and H
    (v1: implicit deadlines only, so releases coincide with deadlines);
  - at each boundary t0, plane [t0, t1): budgets = self.budget(...), checked,
    then plan = self.schedule_plane(budgets, speeds, t1 - t0);
  - decide(t) replays the plan in force at t.

A subclass defines schedule_plane(). The allocation (budget policy) is a
parameter: dp_fair (b = u * length) by default, so DP + dp_fair = DP-fair.

Sporadic releases (PCG*_S paper, Sec. 6). A job released inside the current
plane [t0, t_f) triggers an A-event at its release a: the rest of the plane
[a, t_f) is solved again by schedule_plane(), with the budget left to each job
of the plane and the budget of the new job. The local schedulers start with
LRPT-FM, so this is "LRPT-FM at every A-event, PCG* rules in between".
The TL-plane construction is a parameter, split:
  - "static"  : t_f = min(d_next, t0 + T_min) (eq. 5). A new job's deadline
                is >= t_f: t_f is unchanged, the new job gets (t_f - a) u.
  - "dynamic" : t_f = d_next. If a new job's deadline d is >= t_f, same as
                static. Otherwise [a, t_f) is split into [a, d) and [d, t_f):
                the budgets left are shared in proportion to the lengths, the
                new job gets C (= u (d - a)) in [a, d), the plane ends at d and
                [d, t_f) is opened at d with the budgets kept for it.
"""

from __future__ import annotations

from fractions import Fraction

from ...engine.errors import BudgetInfeasible
from ...trace.trace import PlaneRecord
from ..base import Decision, Scheduler
from .budgets import dp_fair


class DP(Scheduler):
    name = "dp"

    def __init__(self, budget=dp_fair, split="static"):
        self.budget = budget
        self.split = split

    # -------------------------------------------------------------- to define
    def schedule_plane(self, budgets, speeds, length):
        """budgets[i] > 0 for local job i, speeds non-increasing, plane [0, length).
        Returns one list per processor of (i, (start, end)), times in [0, length]."""
        raise NotImplementedError

    # -------------------------------------------------------------- interface
    def init(self, taskset, horizon):
        super().init(taskset, horizon)
        if not all(t.implicit for t in taskset.tasks):
            raise NotImplementedError("DP v1: implicit deadlines only")
        self.T_min = min(t.T for t in taskset.tasks)
        self._deadlines = []     # absolute deadlines of released jobs (known deadlines)
        self._t1 = Fraction(0)
        self._plan = []          # (proc, job, start, end), absolute times
        self._planes = []
        if self.split not in ("static", "dynamic"):
            raise ValueError(f"split must be 'static' or 'dynamic', got {self.split!r}")
        self._t0 = Fraction(0)
        self._budget = {}        # job -> its budget in the current plane [t0, t1)
        self._rem0 = {}          # job -> its remaining work when it entered the plane
        self._arrivals = []      # jobs released inside the current plane (A-events)
        self._pending = []       # dynamic: next planes of a split plane, [(t0, t1, {job: budget})]
        self._late = []          # jobs released at the start of a kept plane

    def on_release(self, job, t):
        self._deadlines.append(job.deadline)
        if t < self._t1:
            self._arrivals.append(job)

    def plane_end(self, t0):
        """End of the TL-plane opened at t0, clipped to the horizon, where d_next is
        the earliest known absolute deadline: deadline > t0 of a job released at or
        before t0 (completed or not). None if no such job (no plane: idle).
          static  (eq. 5): t_f = min(d_next, t0 + T_min)
          dynamic        : t_f = d_next
        Periodic synchronous releases: d_next <= t0 + T_min, so both give d_next."""
        self._deadlines = [d for d in self._deadlines if d > t0]
        if not self._deadlines:
            return None
        end = min(self._deadlines)
        if self.split == "static":
            end = min(end, t0 + self.T_min)
        return min(end, Fraction(self.horizon))

    def decide(self, t, view):
        if t >= self._t1:
            self._new_plane(t, view)
        elif self._arrivals:
            self._a_event(t, view)
        assignment = {}
        wake = self._t1
        for p, job, s, e in self._plan:
            if s <= t < e:
                assignment[p] = job
            if s > t:
                wake = min(wake, s)
            if e > t:
                wake = min(wake, e)
        return Decision(assignment=assignment, wake_at=wake if wake > t else None)

    def trace_planes(self):
        return self._planes

    # -------------------------------------------------------------- internals
    def _new_plane(self, t, view):
        self._plan = []
        self._arrivals = []
        self._late = []
        opened = self._plane_budgets(t, view)
        if opened is None:
            self._budget, self._rem0 = {}, {}
            return
        t0, t1, local = opened
        self._t0 = t0
        self._budget = dict(local)
        self._rem0 = {j: view.remaining(j) for j, _ in local}
        if self._late:
            self._arrivals, self._late = self._late, []
            self._a_event(t0, view)
        else:
            self._solve(t0, t1, local)

    def _solve(self, t, t1, local):
        """Schedule [t, t1) with local = [(job, budget > 0)] and keep the plan."""
        self._plan = []
        if not local:
            return
        plan = self.schedule_plane([b for _, b in local], self.platform.speeds, t1 - t)
        for p, proc_sched in enumerate(plan):
            for i, (s, e) in proc_sched:
                if s < e:
                    self._plan.append((p, local[i][0], t + s, t + e))

    def _a_event(self, t, view):
        """Jobs released at t inside the plane [t0, t1): see the module docstring.
        Each segment is (start, end, {job: budget}); segs[0] is [t, t1), the
        others are the planes kept for later by dynamic splits."""
        if self.budget is not dp_fair:
            raise NotImplementedError(f"{self.name}: A-events are defined for the dp_fair allocation only")
        left = {j: self._budget[j] - (self._rem0[j] - view.remaining(j)) for j in self._budget}
        for j, b in left.items():
            if b < 0:
                raise RuntimeError(f"t={t}: {j} executed more than its budget in the plane")
        segs = [(t, self._t1, dict(left))] + self._pending
        new = sorted(self._arrivals, key=lambda j: (j.task_id, j.k))
        for job in new:
            if job.release != t:
                raise RuntimeError(f"t={t}: A-event of {job} released at {job.release}")
            d = job.deadline
            if d < segs[0][1] and self.split == "static":
                raise RuntimeError(f"t={t}: {job} has its deadline {d} inside the plane ending at "
                                   f"{segs[0][1]} (static TL-planes)")
            for i, (s, e, b) in enumerate(segs):
                if s < d < e:            # dynamic split of [s, e) at d
                    segs[i:i + 1] = [(s, d, {j: x * (d - s) / (e - s) for j, x in b.items()}),
                                     (d, e, {j: x * (e - d) / (e - s) for j, x in b.items()})]
                    break
            u = job.C / (job.deadline - job.release)
            for s, e, b in segs:
                if s < d:                # d is now a segment end
                    b[job] = u * (e - s)
        s0, t1, now = segs[0]
        self._pending = segs[1:]
        self._t1 = t1
        for j in left:                   # budget moved to later planes leaves this plane
            self._budget[j] -= left[j] - now[j]
        for job in new:
            self._budget[job] = now[job]
            self._rem0[job] = view.remaining(job)
        self._arrivals = []

        local = [(j, now[j]) for j in sorted(now, key=lambda j: (j.task_id, j.k)) if now[j] > 0]
        for j, b in local:
            if b > view.remaining(j):
                raise BudgetInfeasible(f"t={t}: budget {b} of {j} > remaining {view.remaining(j)}")
        self._check_horvath([b for _, b in local], self.platform.speeds, t1 - t, t)
        self._check_no_deadline_inside(self._t0, t1)
        jobs = sorted(self._budget, key=lambda j: (j.task_id, j.k))
        self._planes[-1] = PlaneRecord(self._t0, t1, tuple((j, self._budget[j]) for j in jobs))
        self._solve(t, t1, local)

    def _check_no_deadline_inside(self, t0, t1):
        """Required by the TL-plane algorithms: no known deadline strictly inside a plane."""
        for d in self._deadlines:
            if t0 < d < t1:
                raise RuntimeError(f"deadline {d} strictly inside the TL-plane [{t0}, {t1})")

    def _plane_budgets(self, t, view):
        """Start of the plane at t: boundaries, budgets, checks, PlaneRecord.
        Returns (t0, t1, [(job, budget > 0)]), jobs in (task id, k) order,
        or None if no plane is opened (no known deadline after t: idle until
        the next release, at which the engine calls decide again).
        Shared by DP (whole plane computed here) and DPOnline (decided online)."""
        # local jobs in (task id, k) order: fixes the tie-breaking of the local
        # scheduler and matches the job order of the reference implementation
        jobs = sorted(view.active, key=lambda j: (j.task_id, j.k))
        if self._pending:                # dynamic: plane kept by a split
            t0, t1, kept = self._pending.pop(0)
            if t0 != t:
                raise RuntimeError(f"t={t}: kept plane [{t0}, {t1}) opened at {t}")
            for j, b in kept.items():
                if b > 0 and j not in jobs:
                    raise RuntimeError(f"t={t}: {j} completed with budget {b} kept for [{t0}, {t1})")
            budgets = [kept.get(j, Fraction(0)) for j in jobs]
            self._t1 = t1
            # released at t0, after the split: handled as A-events at t0 (by DP)
            self._late = [j for j in jobs if j.release == t and j not in kept]
        else:
            t1 = self.plane_end(t)
            if t1 is None:
                self._t1 = t
                return None
            t0 = t
            self._t1 = t1
            budgets = [Fraction(b) for b in self.budget(jobs, (t0, t1), self, view)]
        length = t1 - t0
        speeds = self.platform.speeds
        if len(budgets) != len(jobs):
            raise BudgetInfeasible(f"t={t0}: {len(budgets)} budgets for {len(jobs)} jobs")
        for j, b in zip(jobs, budgets):
            if not 0 <= b <= view.remaining(j):
                raise BudgetInfeasible(f"t={t0}: budget {b} of {j} outside [0, {view.remaining(j)}]")
        self._check_horvath(budgets, speeds, length, t0)
        self._check_no_deadline_inside(t0, t1)
        self._planes.append(PlaneRecord(t0, t1, tuple(zip(jobs, budgets))))

        # jobs with a zero budget do not take part in the plane
        return t0, t1, [(j, b) for j, b in zip(jobs, budgets) if b > 0]

    @staticmethod
    def _check_horvath(budgets, speeds, length, t0):
        b = sorted(budgets, reverse=True)
        m = len(speeds)
        acc_b = acc_s = Fraction(0)
        for k in range(1, min(m - 1, len(b)) + 1):
            acc_b += b[k - 1]
            acc_s += speeds[k - 1]
            if acc_b > acc_s * length:
                raise BudgetInfeasible(f"t={t0}: {k} largest budgets {acc_b} > S_{k} * {length}")
        if sum(b) > sum(speeds) * length:
            raise BudgetInfeasible(f"t={t0}: total budget {sum(b)} > S_m * {length}")
