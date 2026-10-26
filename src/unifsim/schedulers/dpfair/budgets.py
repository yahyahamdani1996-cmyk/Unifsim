"""Budget policies for DP-fair schedulers.

Signature: policy(jobs, plane, scheduler, view) -> list[Fraction], one budget
per job, in the order of `jobs`. `plane` = (t0, t1).
"""

from __future__ import annotations

from fractions import Fraction


def nominal(jobs, plane, scheduler, view):
    """DP-fair allocation: b_i = u_i * (t1 - t0)."""
    t0, t1 = plane
    length = t1 - t0
    return [scheduler.taskset.task(j.task_id).u * length for j in jobs]


def bounds(job, plane, scheduler, view):
    """(b_inf, b_sup) of a job in a plane, as in both existing simulators:
    b_inf = max(0, rem - u (d - t1)),  b_sup = min(rem, s_1 (t1 - t0))."""
    t0, t1 = plane
    u = scheduler.taskset.task(job.task_id).u
    rem = view.remaining(job)
    b_inf = max(Fraction(0), rem - u * (job.deadline - t1))
    b_sup = min(rem, scheduler.platform.speeds[0] * (t1 - t0))
    return b_inf, b_sup
