import random
from fractions import Fraction as F

import pytest

from unifsim.engine import DeadlineMiss, InvalidDecision, simulate
from unifsim.model import Platform, Task, System
from unifsim.schedulers import Decision, Scheduler
from unifsim.schedulers.global_ import GEDF
from unifsim.validate import validate


def test_exact_completion_on_fast_processor():
    # C = 3 on speed 2 completes at 3/2 exactly
    ts = System((Task(0, 3, 4),), Platform((2, 1)))
    tr = simulate(ts, GEDF())
    validate(ts, tr)
    assert [(s.proc, s.start, s.end) for s in tr.segments] == [(0, 0, F(3, 2))]


def test_edf_uniprocessor_schedule():
    # U = 1/2 + 1/3 + 1/6 = 1 on one processor: EDF is optimal
    ts = System((Task(0, 1, 2), Task(1, 1, 3), Task(2, 1, 6)), Platform((1,)))
    tr = simulate(ts, GEDF())
    validate(ts, tr)
    got = [(s.job.name, s.start, s.end) for s in tr.segments]
    # deadline ties (6 at t=3 and t=4) are broken by task id
    assert got == [
        ("T0_0", 0, 1), ("T1_0", 1, 2), ("T0_1", 2, 3),
        ("T1_1", 3, 4), ("T0_2", 4, 5), ("T2_0", 5, 6),
    ]


def test_edf_uniprocessor_random_never_misses():
    rng = random.Random(1)
    periods = [2, 3, 4, 5, 6, 10, 12]
    for _ in range(200):
        n = rng.randint(1, 6)
        # integer weights, normalised so that U <= 1 exactly
        w = [rng.randint(1, 20) for _ in range(n)]
        target = F(rng.randint(1, 10), 10)
        tasks = []
        for i in range(n):
            T = rng.choice(periods)
            u = target * w[i] / sum(w)
            tasks.append(Task(i, u * T, T))
        ts = System(tuple(tasks), Platform((1,)))
        assert ts.U <= 1
        validate(ts, simulate(ts, GEDF()))


def test_deadline_miss_detected():
    ts = System((Task(0, 2, 2), Task(1, 1, 2)), Platform((1,)))  # U = 3/2 > 1
    with pytest.raises(DeadlineMiss):
        simulate(ts, GEDF())


class _Bad(Scheduler):
    def __init__(self, mode):
        self.mode = mode

    def decide(self, t, view):
        j = view.active[0]
        if self.mode == "two_procs":
            return Decision({0: j, 1: j})
        if self.mode == "wake_now":
            return Decision({0: j}, wake_at=t)
        if self.mode == "bad_proc":
            return Decision({5: j})
        return None


@pytest.mark.parametrize("mode", ["two_procs", "wake_now", "bad_proc", "none"])
def test_invalid_decisions_rejected(mode):
    ts = System((Task(0, 1, 4),), Platform((2, 1)))
    with pytest.raises(InvalidDecision):
        simulate(ts, _Bad(mode))


def test_custom_horizon():
    ts = System((Task(0, 1, 2),), Platform((1,)))
    tr = simulate(ts, GEDF(), horizon=5)   # job 2 released at 4, deadline 6 > 5
    validate(ts, tr)
    assert tr.horizon == 5 and tr.segments[-1].end == 5
