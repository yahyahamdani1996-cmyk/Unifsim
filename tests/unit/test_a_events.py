"""A-events (jobs released inside a TL-plane), static and dynamic TL-planes (PCG*_S, Sec. 6)."""

import random
from collections import defaultdict
from fractions import Fraction as F

import pytest

from unifsim.engine import simulate
from unifsim.gen.platforms import random_platform
from unifsim.model import Platform, System, Task
from unifsim.model.arrivals import Sporadic
from unifsim.model.task import Job
from unifsim.schedulers.registry import make
from unifsim.validate import validate


def random_system(seed, n=5, m=3, y=F(9, 10)):
    """Horvath-feasible system: integer periods in [2, 12], total utilisation y * S_m."""
    rng = random.Random(seed)
    platform = random_platform(m, 1, 6, seed=seed)
    while True:
        w = [rng.randint(1, 100) for _ in range(n)]
        U = y * sum(platform.speeds)
        us = [U * x / sum(w) for x in w]
        tasks = tuple(Task(i, u * T, T) for i, (u, T) in enumerate(
            (u, rng.randint(2, 12)) for u in us))
        system = System(tasks=tasks, platform=platform)
        if system.horvath_feasible():
            return system


def budgets_by_job(trace):
    out = defaultdict(F)
    for p in trace.planes:
        for j, b in p.budgets:
            out[j] += b
    return out


def run(system, name, alpha, seed, horizon):
    arr = Sporadic(alpha=alpha, seed=seed, first_release="random")
    trace = simulate(system, make(name), horizon=horizon, arrivals=arr)
    validate(system, trace, arr)        # every job meets its deadline
    return trace, arr


# ------------------------------------------------------------------ the miss of the first trace
def test_t1_1_gets_its_budget_inside_the_plane():
    system = System(tasks=(Task(0, 2, 4), Task(1, 3, 6)), platform=Platform((2, 1)))
    arr = Sporadic(alpha=1, seed=3)
    trace = simulate(system, make("pcg_star"), horizon=20, arrivals=arr)
    validate(system, trace, arr)
    t1_1 = [(p.t0, p.t1, b) for p in trace.planes for j, b in p.budgets if (j.task_id, j.k) == (1, 1)]
    # released at 192/25 inside [796/125, 1296/125): (t_f - a) u, then u * length
    assert t1_1 == [(F(796, 125), F(1296, 125), F(168, 125)),
                    (F(1296, 125), F(342, 25), F(207, 125))]
    assert sum(b for _, _, b in t1_1) == 3


# ------------------------------------------------------------------ random sporadic runs
CASES = [(seed, alpha) for seed in range(12) for alpha in (F(1, 4), 1, 3)]


@pytest.mark.parametrize("split", ["", "_dyn"])
@pytest.mark.parametrize("base", ["pcg_star", "pcg_star_v2"])
@pytest.mark.parametrize("seed,alpha", CASES)
def test_random_sporadic_no_miss_and_dp_fair(seed, alpha, base, split):
    system = random_system(seed)
    H = 4 * max(t.T for t in system.tasks)
    trace, arr = run(system, base + split, alpha, seed, H)
    end = max(p.t1 for p in trace.planes)
    for j, total in budgets_by_job(trace).items():
        if j.deadline <= end:                       # jobs not cut by the horizon
            assert total == j.C, (j, total)          # budgets of a job sum to C
    bounds = {p.t0 for p in trace.planes} | {p.t1 for p in trace.planes}
    for j in arr.jobs(system, H):
        if j.deadline <= end:
            assert j.deadline in bounds              # every deadline is a boundary


def test_dynamic_splits_are_exercised():
    """Some runs above must differ between static and dynamic (otherwise the
    split code would not be tested)."""
    differ = 0
    for seed, alpha in CASES:
        system = random_system(seed)
        H = 4 * max(t.T for t in system.tasks)
        st, _ = run(system, "pcg_star", alpha, seed, H)
        dy, _ = run(system, "pcg_star_dyn", alpha, seed, H)
        differ += [(p.t0, p.t1) for p in st.planes] != [(p.t0, p.t1) for p in dy.planes]
    assert differ > 0


# ------------------------------------------------------------------ periodic: nothing changes
@pytest.mark.parametrize("seed", range(6))
def test_periodic_static_equals_dynamic(seed):
    system = random_system(seed)
    st = simulate(system, make("pcg_star"))
    dy = simulate(system, make("pcg_star_dyn"))
    assert st.segments == dy.segments
    assert [(p.t0, p.t1) for p in st.planes] == [(p.t0, p.t1) for p in dy.planes]


# ------------------------------------------------------------------ paper, end of Sec. 6.1
class TminPeriodic(Sporadic):
    """Sporadic releases, except the task of period T_min: strictly periodic from 0."""

    def jobs(self, system, horizon):
        tmin = min(system.tasks, key=lambda t: (t.T, t.id))
        out = [j for j in super().jobs(system, horizon) if j.task_id != tmin.id]
        k = 0
        while k * tmin.T < horizon:
            out.append(Job.of(tmin, k))
            k += 1
        out.sort(key=lambda j: (j.release, j.task_id, j.k))
        return out


@pytest.mark.parametrize("seed", range(8))
def test_tmin_strictly_periodic_same_planes(seed):
    """'If a task with period T_min is strictly periodic, the dynamic approach
    produces the same TL-plane boundaries as the static approach.'"""
    system = random_system(seed)
    H = 4 * max(t.T for t in system.tasks)
    arr = TminPeriodic(alpha=1, seed=seed, first_release="random")
    st = simulate(system, make("pcg_star"), horizon=H, arrivals=arr)
    dy = simulate(system, make("pcg_star_dyn"), horizon=H, arrivals=arr)
    assert [(p.t0, p.t1) for p in st.planes] == [(p.t0, p.t1) for p in dy.planes]


# ------------------------------------------------------------------ guards
def test_online_schedulers_refuse_a_events():
    system = System(tasks=(Task(0, 2, 4), Task(1, 3, 6)), platform=Platform((2, 1)))
    with pytest.raises(NotImplementedError):
        simulate(system, make("pcg_star_online"), horizon=20, arrivals=Sporadic(alpha=1, seed=3))


def test_a_events_need_dp_fair():
    system = System(tasks=(Task(0, 2, 4), Task(1, 3, 6)), platform=Platform((2, 1)))
    with pytest.raises(NotImplementedError):
        simulate(system, make("wc_pcg_star"), horizon=20, arrivals=Sporadic(alpha=1, seed=3))
