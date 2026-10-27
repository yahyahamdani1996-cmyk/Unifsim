"""Building blocks of an event-driven scheduler inside one TL-plane
on a uniform platform: processors with remaining capacity, jobs with remaining
work, assignment, B/C events, merging of the produced plan.

Taken from the PCG reference implementation by Antoine Bertout and Pascal
Richard (src/pcg/models.py, src/pcg/scheduler.py), logic unchanged.
The original code has no license yet: its authors' agreement is required
before this file is distributed.
"""

from __future__ import annotations

from enum import Enum
from fractions import Fraction


class Proc:
    def __init__(self, speed, window_size, idx):
        self.speed = speed
        self.rem_capacity = Fraction(speed * window_size)
        self.idx = idx
        self.current_job = None


class EventType(Enum):
    C = 1  # value = priority in treatment
    B = 0


class LocalJob:
    """A job inside one TL-plane: its index i in the budget list and its remaining budget
    (not the model Job, which has a release and a deadline)."""

    def __init__(self, idx, execution_time):
        self.idx = idx
        self.remaining_time = execution_time
        self.assigned_proc = None


class Event:
    def __init__(self, type, job, delta, proc=None):
        self.type, self.job, self.proc, self.delta = type, job, proc, delta

    def __lt__(self, other):
        return (self.delta, -self.type.value) < (other.delta, -other.type.value)


def assign(job, proc):
    job.assigned_proc = proc
    proc.current_job = job


def unassign(job):
    proc = job.assigned_proc
    if proc is None:
        raise RuntimeError(f"job {job.idx} was not assigned to any proc")
    proc.current_job = None
    job.assigned_proc = None


def compute_next_event(job, processors):
    m = len(processors)
    k = 0
    while k < m and job.remaining_time <= processors[k].rem_capacity:
        k += 1

    if job.assigned_proc:  # running job
        if k == m:  # B-event
            delta = job.remaining_time / job.assigned_proc.speed
            return Event(EventType.B, job, delta, job.assigned_proc)
        if k > 0 and job.assigned_proc.speed <= processors[k].speed:
            proc = processors[k - 1]  # below
        else:
            proc = processors[k]      # above
        speed = job.assigned_proc.speed
    else:  # unassigned
        proc = processors[k - 1]
        speed = 0

    delta = (job.remaining_time - proc.rem_capacity) / (speed - proc.speed)
    if delta < 0:
        return None
    return Event(EventType.C, job, delta, proc)


def flatten(schedule):
    out = []
    for proc_sched in schedule:
        p = []
        for job_id, (start, end) in proc_sched:
            if p and p[-1][0] == job_id and p[-1][1][1] == start:
                p[-1] = (job_id, (p[-1][1][0], end))
            else:
                p.append((job_id, (start, end)))
        out.append(p)
    return out
