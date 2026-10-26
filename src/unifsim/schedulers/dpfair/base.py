"""DPFair: base class of all DP-fair (TL-plane) schedulers.

It implements the Scheduler interface once:
  - TL-plane boundaries = all deadlines in (0, H], plus 0 and H
    (v1: implicit deadlines only, so releases coincide with deadlines);
  - at each boundary t0, plane [t0, t1): budgets = self.budget(...), checked,
    then plan = self.schedule_plane(budgets, speeds, t1 - t0);
  - decide(t) replays the plan in force at t.

A subclass defines schedule_plane(). The budget policy is a parameter.
"""

from __future__ import annotations

from fractions import Fraction

from ...engine.errors import BudgetInfeasible
from ...trace.trace import PlaneRecord
from ..base import Decision, Scheduler
from .budgets import nominal


class DPFair(Scheduler):
    name = "dpfair"

    def __init__(self, budget=nominal):
        self.budget = budget

    # -------------------------------------------------------------- to define
    def schedule_plane(self, budgets, speeds, length):
        """budgets[i] > 0 for local job i, speeds non-increasing, plane [0, length).
        Returns one list per processor of (i, (start, end)), times in [0, length]."""
        raise NotImplementedError

    # -------------------------------------------------------------- interface
    def init(self, taskset, horizon):
        super().init(taskset, horizon)
        if not all(t.implicit for t in taskset.tasks):
            raise NotImplementedError("DPFair v1: implicit deadlines only")
        bounds = {Fraction(0), Fraction(horizon)}
        for t in taskset.tasks:
            d = t.T
            while d < horizon:
                bounds.add(Fraction(d))
                d += t.T
        self.boundaries = sorted(bounds)
        self._plane_idx = -1
        self._t1 = Fraction(0)
        self._plan = []          # (proc, job, start, end), absolute times
        self._planes = []

    def decide(self, t, view):
        if t >= self._t1:
            self._new_plane(t, view)
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
        self._plane_idx = self.boundaries.index(t)   # t is always a boundary here
        t0, t1 = t, self.boundaries[self._plane_idx + 1]
        self._t1 = t1
        length = t1 - t0
        speeds = self.platform.speeds

        # local jobs in (task id, k) order: fixes the tie-breaking of the local
        # scheduler and matches the job order of the reference implementation
        jobs = sorted(view.active, key=lambda j: (j.task_id, j.k))
        budgets = [Fraction(b) for b in self.budget(jobs, (t0, t1), self, view)]
        if len(budgets) != len(jobs):
            raise BudgetInfeasible(f"t={t0}: {len(budgets)} budgets for {len(jobs)} jobs")
        for j, b in zip(jobs, budgets):
            if not 0 <= b <= view.remaining(j):
                raise BudgetInfeasible(f"t={t0}: budget {b} of {j} outside [0, {view.remaining(j)}]")
        self._check_horvath(budgets, speeds, length, t0)
        self._planes.append(PlaneRecord(t0, t1, tuple(zip(jobs, budgets))))

        # jobs with a zero budget do not take part in the plane
        local = [(j, b) for j, b in zip(jobs, budgets) if b > 0]
        self._plan = []
        if not local:
            return
        plan = self.schedule_plane([b for _, b in local], speeds, length)
        for p, proc_sched in enumerate(plan):
            for i, (s, e) in proc_sched:
                if s < e:
                    self._plan.append((p, local[i][0], t0 + s, t0 + e))

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
