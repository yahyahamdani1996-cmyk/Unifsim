"""DPOnline: deadline-partitioned schedulers that decide ONLINE inside each TL-plane.

Same TL-planes, allocations (budget=...) and checks as DP. The difference:
  DP       : at the start of a plane, schedule_plane() computes the whole plane;
             decide() then replays that plan.            (reference implementation)
  DPOnline : at the start of a plane, plane_start() initialises the plane state;
             at EVERY scheduling point, decide_in_plane(t) says who runs now and
             when the next event is.                     (shrimp philosophy)

A subclass defines:
    plane_start(t0, t1, jobs, budgets)   jobs: model jobs with budget > 0, (task id, k) order
    decide_in_plane(t) -> (assignment {processor index: job}, next event time or None)
and can call self.local_remaining(job): budget left in the current plane.
All events at time t must be handled inside decide_in_plane(t): the next event
time it returns must be > t.
"""

from __future__ import annotations

from fractions import Fraction

from ..base import Decision
from .base import DP


class DPOnline(DP):
    name = "dp_online"

    def plane_start(self, t0, t1, jobs, budgets):
        raise NotImplementedError

    def decide_in_plane(self, t):
        raise NotImplementedError

    def schedule_plane(self, budgets, speeds, length):   # not used by online schedulers
        raise NotImplementedError("DPOnline decides online: see decide_in_plane")

    def local_remaining(self, job) -> Fraction:
        executed = self._rem0[job] - self._view.remaining(job)
        return self._budget[job] - executed

    def decide(self, t, view):
        self._view = view
        if t >= self._t1:
            t0, t1, local = self._plane_budgets(t, view)
            self._budget = dict(local)
            self._rem0 = {j: view.remaining(j) for j, _ in local}
            self.plane_start(t0, t1, [j for j, _ in local], self._budget)
        assignment, nxt = self.decide_in_plane(t)
        wake = self._t1 if nxt is None else min(nxt, self._t1)
        if wake <= t:
            raise RuntimeError(f"{self.name}: next event {nxt} not after t={t} (events at t must be handled)")
        return Decision(assignment=assignment, wake_at=wake)
