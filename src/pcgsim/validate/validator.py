"""Independent validator. Reads only the task set and the trace.

It shares no code with the engine or the schedulers: job releases, deadlines
and execution times are recomputed here from the Task fields, and the work
of each job is re-accumulated from the segments.

General invariants (all algorithms):
  V0  every segment refers to an existing job
  V1  segments well formed: 0 <= start < end <= horizon
  V2  no overlap of two segments on one processor
  V3  no job on two processors at the same time
  V4  no execution before release
  V5  executed work == C for jobs with deadline <= horizon, <= C otherwise
  V6  completion <= deadline
  V7  every job released before the horizon with deadline <= horizon appears
"""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction


class ValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")


def _expected_jobs(taskset, horizon):
    """(task_id, k) -> (release, deadline, C, task), recomputed from the tasks."""
    out = {}
    for task in taskset.tasks:
        k = 0
        while k * task.T < horizon:
            r = Fraction(k * task.T)
            out[(task.id, k)] = (r, r + task.D, Fraction(task.C))
            k += 1
    return out


def validate(taskset, trace) -> None:
    H = Fraction(trace.horizon)
    speeds = taskset.platform.speeds
    if trace.m != len(speeds):
        raise ValidationError("V0", f"trace has m={trace.m}, platform has {len(speeds)}")
    expected = _expected_jobs(taskset, H)

    per_proc = defaultdict(list)
    per_job = defaultdict(list)
    for s in trace.segments:
        key = (s.job.task_id, s.job.k)
        if key not in expected:
            raise ValidationError("V0", f"segment of unknown job {key}")
        if not (0 <= s.proc < len(speeds)):
            raise ValidationError("V0", f"segment on unknown processor {s.proc}")
        if not (0 <= s.start < s.end <= H):
            raise ValidationError("V1", f"bad segment {key} on P{s.proc}: [{s.start}, {s.end}) with H={H}")
        per_proc[s.proc].append((s.start, s.end, key))
        per_job[key].append((s.start, s.end, s.proc))

    for p, segs in per_proc.items():
        segs.sort()
        for (a0, a1, ka), (b0, b1, kb) in zip(segs, segs[1:]):
            if a1 > b0:
                raise ValidationError("V2", f"P{p}: {ka} [{a0},{a1}) overlaps {kb} [{b0},{b1})")

    for key, segs in per_job.items():
        segs.sort()
        release, deadline, C = expected[key]
        for (a0, a1, pa), (b0, b1, pb) in zip(segs, segs[1:]):
            if a1 > b0:
                raise ValidationError("V3", f"{key} runs on P{pa} and P{pb} at the same time ({b0} < {a1})")
        if segs[0][0] < release:
            raise ValidationError("V4", f"{key} starts at {segs[0][0]} before its release {release}")
        work = sum(((e - s) * speeds[p] for s, e, p in segs), Fraction(0))
        if deadline <= H:
            if work != C:
                raise ValidationError("V5", f"{key} executed {work}, expected C={C}")
            if segs[-1][1] > deadline:
                raise ValidationError("V6", f"{key} completes at {segs[-1][1]} after its deadline {deadline}")
        elif work > C:
            raise ValidationError("V5", f"{key} executed {work} > C={C}")

    for key, (release, deadline, C) in expected.items():
        if deadline <= H and key not in per_job:
            raise ValidationError("V7", f"{key} (release {release}, deadline {deadline}) never executes")
