from fractions import Fraction as F

import pytest

from unifsim.engine import simulate
from unifsim.model import Periodic, Platform, Sporadic, System, Task
from unifsim.schedulers.global_ import GEDF
from unifsim.validate import validate


def _system():
    return System((Task(0, 2, 4), Task(1, 3, 6), Task(2, 5, 10)), Platform((2, 1)))


def _by_task(jobs):
    out = {}
    for j in jobs:
        out.setdefault(j.task_id, []).append(j)
    return out


def test_alpha_zero_is_periodic():
    ts = _system()
    assert Sporadic(alpha=0, seed=7).jobs(ts, 60) == Periodic().jobs(ts, 60)


@pytest.mark.parametrize("alpha", [F(1, 4), 1, 3])
def test_gaps_in_bounds_and_deadlines(alpha):
    ts = _system()
    jobs = Sporadic(alpha=alpha, seed=3).jobs(ts, 200)
    for tid, js in _by_task(jobs).items():
        T = ts.task(tid).T
        assert [j.k for j in js] == list(range(len(js)))
        for j in js:
            assert j.deadline == j.release + T and j.C == ts.task(tid).C
        for a, b in zip(js, js[1:]):
            assert T <= b.release - a.release <= T * (1 + alpha)


def test_sorted_and_before_horizon():
    jobs = Sporadic(alpha=1, seed=1, first_release="random").jobs(_system(), 100)
    assert all(j.release < 100 for j in jobs)
    assert jobs == sorted(jobs, key=lambda j: (j.release, j.task_id, j.k))
    assert all(0 <= j.release for j in jobs)


def test_first_release_random_in_first_period():
    ts = _system()
    jobs = Sporadic(alpha=0, seed=5, first_release="random").jobs(ts, 100)
    for tid, js in _by_task(jobs).items():
        assert 0 <= js[0].release < ts.task(tid).T


def test_deterministic_and_paired_across_alpha():
    ts = _system()
    assert Sporadic(alpha=1, seed=9).jobs(ts, 100) == Sporadic(alpha=1, seed=9).jobs(ts, 100)
    # same seed: the j-th draw U is the same for every alpha
    g1 = _by_task(Sporadic(alpha=1, seed=9).jobs(ts, 1000))
    g2 = _by_task(Sporadic(alpha=2, seed=9).jobs(ts, 1000))
    for tid in g1:
        T = ts.task(tid).T
        u1 = [(b.release - a.release - T) / T for a, b in zip(g1[tid], g1[tid][1:])]
        u2 = [(b.release - a.release - T) / (2 * T) for a, b in zip(g2[tid], g2[tid][1:])]
        n = min(len(u1), len(u2))
        assert u1[:n] == u2[:n]


def test_invalid_parameters():
    with pytest.raises(ValueError):
        Sporadic(alpha=-1)
    with pytest.raises(TypeError):
        Sporadic(alpha=0.5)
    with pytest.raises(ValueError):
        Sporadic(first_release="late")


def test_engine_runs_gedf_on_sporadic_arrivals():
    ts = System((Task(0, 1, 4), Task(1, 1, 6)), Platform((2, 1)))
    arr = Sporadic(alpha=1, seed=2)
    trace = simulate(ts, GEDF(), horizon=60, arrivals=arr)
    assert trace.meta["arrivals"] == arr.to_dict()
    validate(ts, trace, arrivals=arr)


def _planes(tasks, releases, horizon):
    """Plane sequence produced by DP.plane_end for fixed release dates."""
    from unifsim.model import Job
    from unifsim.schedulers.dp.base import DP
    ts = System(tuple(Task(i, 1, T) for i, T in tasks.items()), Platform((1,)))
    dp = DP()
    dp.init(ts, horizon)
    jobs = sorted((Job(i, k, F(a), F(a) + tasks[i], F(1)) for i in releases for k, a in enumerate(releases[i])),
                  key=lambda j: j.release)
    planes, t0, nxt = [], F(0), 0
    while t0 < horizon:
        while nxt < len(jobs) and jobs[nxt].release <= t0:
            dp.on_release(jobs[nxt], jobs[nxt].release)
            nxt += 1
        tf = dp.plane_end(t0)
        if tf is None:
            if nxt == len(jobs):
                break
            t0 = jobs[nxt].release
            continue
        planes.append((t0, tf))
        t0 = tf
    return planes


def test_plane_end_sporadic_example():
    # T = 10, 15, 25 (T_min = 10); cap used at t0 = 23 (tf = 33, not 37)
    planes = _planes({1: 10, 2: 15, 3: 25}, {1: [0, 13, 24], 2: [3], 3: [12]}, 40)
    assert planes == [(0, 10), (10, 18), (18, 23), (23, 33), (33, 34), (34, 37)]


def test_plane_end_idle_starts_at_next_release():
    planes = _planes({1: 4}, {1: [0, 10]}, 20)
    assert planes == [(0, 4), (10, 14)]


def test_plane_end_known_deadline_wins():
    # paper rule: a deadline already known before t0 + T_min ends the plane
    planes = _planes({1: 4, 2: 10}, {1: [1], 2: [0]}, 10)
    assert planes == [(0, 4), (4, 5), (5, 9), (9, 10)]
