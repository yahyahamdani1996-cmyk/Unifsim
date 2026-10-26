import random
from fractions import Fraction as F

import pytest

from unifsim.engine import BudgetInfeasible, simulate
from unifsim.model import Platform, Task, System
from unifsim.schedulers.dp import PCGStar
from unifsim.validate import validate

PERIODS = [2, 3, 4, 5, 6, 10, 12]


def _random_feasible(rng):
    m = rng.randint(1, 5)
    speeds = tuple(sorted([1] + [rng.randint(1, 8) for _ in range(m - 1)], reverse=True))
    n = rng.randint(1, 3 * m)
    while True:
        load = F(rng.randint(1, 20), 20)
        w = [rng.randint(1, 30) for _ in range(n)]
        tasks = tuple(
            Task(i, load * sum(speeds) * wi / sum(w) * T, T)
            for i, (wi, T) in enumerate(zip(w, (rng.choice(PERIODS) for _ in w)))
        )
        ts = System(tasks, Platform(speeds))
        if ts.horvath_feasible():
            return ts


def _work_in(trace, job, t0, t1, speeds):
    return sum(
        (min(s.end, t1) - max(s.start, t0)) * speeds[s.proc]
        for s in trace.segments
        if s.job == job and s.start < t1 and s.end > t0
    )


@pytest.mark.parametrize("seed", range(100))
def test_pcg_star_random_feasible(seed):
    ts = _random_feasible(random.Random(seed))
    tr = simulate(ts, PCGStar())
    validate(ts, tr)
    speeds = ts.platform.speeds
    for plane in tr.planes:
        for job, b in plane.budgets:
            # dp_fair budget, executed exactly inside its plane
            assert b == ts.task(job.task_id).u * (plane.t1 - plane.t0)
            assert _work_in(tr, job, plane.t0, plane.t1, speeds) == b


def test_planes_cover_hyperperiod():
    ts = System((Task(0, 3, 2), Task(1, 2, 3), Task(2, 5, 6)), Platform((2, 1)))
    tr = simulate(ts, PCGStar())
    assert [(p.t0, p.t1) for p in tr.planes] == [(0, 2), (2, 3), (3, 4), (4, 6)]


def test_constrained_deadlines_refused():
    ts = System((Task(0, 1, 4, D=3),), Platform((1,)))
    with pytest.raises(NotImplementedError):
        simulate(ts, PCGStar())


def test_infeasible_budget_refused():
    def too_much(jobs, plane, scheduler, view):
        return [view.remaining(j) for j in jobs]        # whole job in the first plane
    ts = System((Task(0, 4, 4), Task(1, 4, 4), Task(2, 1, 2)), Platform((1, 1)))
    with pytest.raises(BudgetInfeasible):
        simulate(ts, PCGStar(budget=too_much))


@pytest.mark.parametrize("order", ["remaining", "index"])
@pytest.mark.parametrize("seed", range(100))
def test_wc_pcg_star_random_feasible(seed, order):
    from unifsim.schedulers.dp.budgets import greedy_wk
    ts = _random_feasible(random.Random(seed))
    tr = simulate(ts, PCGStar(budget=greedy_wk(order)))
    validate(ts, tr)
    speeds = ts.platform.speeds
    for plane in tr.planes:
        for job, b in plane.budgets:
            assert b >= 0 and _work_in(tr, job, plane.t0, plane.t1, speeds) == b
            # lag bound (b >= b_inf): at the end of each plane, every job has done at
            # least its fluid share u * (t1 - release), the property that keeps optimality
            done = _work_in(tr, job, job.release, plane.t1, speeds)
            assert done >= min(job.C, ts.task(job.task_id).u * (plane.t1 - job.release))


def test_greedy_wk_bad_order():
    from unifsim.schedulers.dp.budgets import greedy_wk
    with pytest.raises(ValueError):
        greedy_wk("deadline")
