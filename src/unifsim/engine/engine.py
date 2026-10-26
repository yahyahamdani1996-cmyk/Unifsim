"""Event-driven engine. Exact time, fixed order for simultaneous events:

    1. completions   2. releases   3. deadline check   4. decide
    5. decision check   6. next instant   7. execute and record   8. advance
"""

from __future__ import annotations

from fractions import Fraction

from ..model.system import System
from ..schedulers.base import Decision, Scheduler, View
from ..trace.trace import Trace
from .errors import DeadlineMiss, InvalidDecision


class Engine:
    def __init__(self, taskset: System, scheduler: Scheduler, horizon=None):
        self.taskset = taskset
        self.scheduler = scheduler
        self.platform = taskset.platform
        self.horizon = Fraction(taskset.hyperperiod if horizon is None else horizon)
        if self.horizon <= 0:
            raise ValueError("horizon must be > 0")

    def run(self) -> Trace:
        ts, plat, sched, H = self.taskset, self.platform, self.scheduler, self.horizon
        m = plat.m
        trace = Trace(m=m, horizon=H, meta={
            "taskset_hash": ts.hash,
            "scheduler": getattr(sched, "name", type(sched).__name__),
        })

        pending = ts.jobs(H)          # sorted by release
        nxt = 0                       # index of next unreleased job
        active: list = []             # released, not completed
        remaining: dict = {}
        sched.init(ts, H)
        running: dict[int, object] = {}
        t = Fraction(0)

        while True:
            # 1. completions
            done = [j for j in active if remaining[j] == 0]
            for j in done:
                active.remove(j)
                sched.on_completion(j, t)
            # 2. releases
            while nxt < len(pending) and pending[nxt].release == t:
                j = pending[nxt]
                nxt += 1
                active.append(j)
                remaining[j] = j.C
                sched.on_release(j, t)
            # 3. deadline check
            for j in active:
                if j.deadline <= t:
                    raise DeadlineMiss(j, t)
            if t >= H:
                break

            # 4. decide
            active.sort(key=lambda j: (j.release, j.task_id, j.k))
            view = View(t, plat, tuple(active), remaining)
            d = sched.decide(t, view)
            trace.decisions.append(t)
            # 5. decision check
            self._check(d, t, active, m)
            running = dict(d.assignment)

            # 6. next instant
            cand = [H]
            if nxt < len(pending):
                cand.append(pending[nxt].release)
            cand.extend(j.deadline for j in active if j.deadline > t)
            if d.wake_at is not None:
                cand.append(d.wake_at)
            for p, j in running.items():
                cand.append(t + remaining[j] / plat.speeds[p])
            t2 = min(cand)
            if t2 <= t:   # cannot happen with the checks above; guard against engine bugs
                raise RuntimeError(f"time does not advance at t={t}")

            # 7. execute and record
            dt = t2 - t
            for p, j in running.items():
                work = dt * plat.speeds[p]
                if work > remaining[j]:
                    raise RuntimeError(f"{j.name} over-executed at t={t}")
                remaining[j] -= work
                trace.add(p, j, t, t2)
            # 8. advance
            t = t2

        trace.planes = list(sched.trace_planes())
        return trace

    @staticmethod
    def _check(d: Decision, t, active, m) -> None:
        if not isinstance(d, Decision):
            raise InvalidDecision(f"decide() must return a Decision, got {type(d).__name__}")
        seen = set()
        act = set(active)
        for p, j in d.assignment.items():
            if not (isinstance(p, int) and 0 <= p < m):
                raise InvalidDecision(f"t={t}: invalid processor index {p!r}")
            if j not in act:
                raise InvalidDecision(f"t={t}: {j} is not active (unreleased or completed)")
            if j in seen:
                raise InvalidDecision(f"t={t}: {j} assigned to two processors")
            seen.add(j)
        if d.wake_at is not None and not d.wake_at > t:
            raise InvalidDecision(f"t={t}: wake_at={d.wake_at} must be > t")


def simulate(taskset: System, scheduler: Scheduler, horizon=None) -> Trace:
    return Engine(taskset, scheduler, horizon).run()
