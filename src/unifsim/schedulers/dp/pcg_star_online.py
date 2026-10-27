"""PCG* decided online (shrimp philosophy).

Port of shrimp src/src_simulator/schedulers/pcg_etoile_tl.py (Y. Hamdani): same
data structures (current / pending / locked assignments, armed events) and same
event handling (all the events of an instant handled together: C-events, then
reassignment of displaced jobs, then B-events). Removed: epsilon tolerances
(exact arithmetic: te == 0 instead of te <= epsilon), simulator timers (the next
event time is returned to the engine), logging, budget matrix and TL trace.
"""

from __future__ import annotations

from fractions import Fraction

from .budgets import dp_fair
from .online import DPOnline


class PCGStarOnline(DPOnline):
    name = "pcg_star_online"

    def __init__(self, budget=dp_fair):
        super().__init__(budget)

    # ------------------------------------------------------------ helpers
    def rate(self, p):
        return self.platform.speeds[p]

    def W(self, t):
        return [(self.tf - t) * self.rate(p) for p in self.sorted_procs]

    # ------------------------------------------------------------ plane start
    def plane_start(self, t0, t1, jobs, budgets):
        self.tf = t1
        self.pi = budgets
        self.sorted_procs = list(range(self.platform.m))     # fastest first
        self.current, self.pending, self.locked = [], [], []
        self.armed = None                                    # (event time, te, events)

        local = sorted((j for j in jobs if budgets[j] > 0), key=lambda j: (-budgets[j], j.task_id))
        m = self.platform.m
        for i, job in enumerate(local):
            if i < m:
                self.current.append((job, self.sorted_procs[i]))
            else:
                self.pending.append(job)

        # initial C-events: a budget equal to a whole processor capacity
        W, events, k = self.W(t0), {}, 0
        used = [False] * len(self.sorted_procs)
        for job in [j for j, _ in self.current] + list(self.pending):
            R = self.local_remaining(job)
            while k < len(self.sorted_procs) and R < W[k]:
                k += 1
            if k < len(self.sorted_procs) and R == W[k] and not used[k]:
                events[job] = (Fraction(0), "C", self.sorted_procs[k])
                used[k] = True
        if events:
            self.handle_events(Fraction(0), events)

    # ------------------------------------------------------------ events
    def compute_events(self, W):
        events = {}
        m = len(self.sorted_procs)
        for job, p in self.current:
            R, S = self.local_remaining(job), self.rate(p)
            if R <= 0:
                events[job] = (Fraction(0), "B", p)
                continue
            k = 0
            while k < m and R <= W[k]:
                k += 1
            if k == m:
                events[job] = (R / S, "B", p)
                continue
            if k > 0 and S <= self.rate(self.sorted_procs[k]):
                target, boundary = self.sorted_procs[k - 1], W[k - 1]
            else:
                target, boundary = self.sorted_procs[k], W[k]
            S_target = self.rate(target)
            if target == p or S == S_target:
                events[job] = (R / S, "B", p)
                continue
            dt = (R - boundary) / (S - S_target)
            if dt >= 0:
                events[job] = (dt, "C", target)

        for job in self.pending:
            R = self.local_remaining(job)
            if R <= 0:
                continue
            k = 0
            while k < m and R <= W[k]:
                k += 1
            if k > 0:
                target = self.sorted_procs[k - 1]
                dt = (W[k - 1] - R) / self.rate(target)
                if dt >= 0:
                    events[job] = (dt, "C", target)

        if not events:
            return None, {}
        return min(dt for dt, _, _ in events.values()), events

    def handle_events(self, te, events):
        free_jobs, free_procs, have_ev_jobs = [], [], []
        current_events, seen = [], set()
        for job, (dt, kind, proc) in events.items():
            if dt != te:
                continue
            if kind == "C":
                if proc in seen:
                    continue
                seen.add(proc)
            have_ev_jobs.append(job)
            current_events.append((job, kind, proc))

        # 1. C-events: pin the job on its processor until the end of the plane
        for job, kind, proc in current_events:
            if kind != "C":
                continue
            if proc in free_procs:
                free_procs.remove(proc)
            if job in free_jobs:
                free_jobs.remove(job)
            if job in self.pending:
                self.pending.remove(job)
            else:
                old = next((p for j, p in self.current if j == job), None)
                if old is not None:
                    self.current.remove((job, old))
                    if old != proc:
                        free_procs.append(old)
            displaced = next((j for j, p in self.current if p == proc), None)
            if displaced is not None and displaced != job:
                self.current.remove((displaced, proc))
                if displaced not in have_ev_jobs:
                    free_jobs.append(displaced)
            self.locked.append((job, proc))
            if proc in self.sorted_procs:
                self.sorted_procs.remove(proc)

        # 2. displaced jobs first, then pending jobs, on the freed processors
        while free_jobs and free_procs:
            self.current.append((free_jobs.pop(0), free_procs.pop(0)))
        while self.pending and free_procs:
            self.current.append((self.pending.pop(0), free_procs.pop(0)))
        if free_jobs:
            self.pending = free_jobs + self.pending

        # 3. B-events: a finished job frees its processor for the next pending job
        for job, kind, _ in current_events:
            if kind != "B":
                continue
            old = next((p for j, p in self.current if j == job), None)
            if old is not None:
                self.current.remove((job, old))
                if self.pending:
                    self.current.append((self.pending.pop(0), old))

    # ------------------------------------------------------------ decisions
    def decide_in_plane(self, t):
        if self.armed is not None:
            at, te, events = self.armed
            self.armed = None
            if at == t:
                self.handle_events(te, events)
        nxt = None
        while True:
            if not self.sorted_procs or (not self.current and not self.pending):
                break
            te, events = self.compute_events(self.W(t))
            if te is None:
                break
            if te == 0:                       # events now: handle them and look again
                self.handle_events(te, events)
                continue
            self.armed = (t + te, te, events)
            nxt = t + te
            break
        assignment = {p: job for job, p in self.current + self.locked}
        return assignment, nxt
