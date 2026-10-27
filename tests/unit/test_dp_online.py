import random
from fractions import Fraction as F

import pytest

from unifsim import Platform, System, Task, run

PERIODS = [2, 3, 4, 5, 6, 10, 12]
RUNNING = System((Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4), Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
                 Platform((6, 3, 2, 2, 1)))


def _segments(r):
    return sorted((x.proc, x.job.task_id, x.job.k, x.start, x.end) for x in r.trace.segments)


@pytest.mark.parametrize("online, reference", [("pcg_star_online", "pcg_star"), ("wc_pcg_star_online", "wc_pcg_star")])
def test_running_example_identical_to_reference(online, reference):
    assert _segments(run(RUNNING, online)) == _segments(run(RUNNING, reference))


def _random_feasible(rng):
    m = rng.randint(1, 5)
    speeds = tuple(sorted([1] + [rng.randint(1, 8) for _ in range(m - 1)], reverse=True))
    n = rng.randint(1, 3 * m)
    while True:
        load = F(rng.randint(1, 20), 20)
        w = [rng.randint(1, 30) for _ in range(n)]
        tasks = tuple(Task(i, load * sum(speeds) * wi / sum(w) * T, T)
                      for i, (wi, T) in enumerate(zip(w, (rng.choice(PERIODS) for _ in w))))
        s = System(tasks, Platform(speeds))
        if s.horvath_feasible():
            return s


@pytest.mark.parametrize("algo", ["pcg_star_online", "wc_pcg_star_online"])
@pytest.mark.parametrize("seed", range(80))
def test_online_valid_on_random_systems(seed, algo):
    s = _random_feasible(random.Random(seed))
    r = run(s, algo)                                   # raises if invalid or a deadline is missed
    assert r.metrics.n_jobs_completed == r.metrics.n_jobs_released or r.trace.horizon < s.hyperperiod
