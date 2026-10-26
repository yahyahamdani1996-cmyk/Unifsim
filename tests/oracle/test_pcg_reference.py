"""Oracle: unifsim PCG* (nominal budget) must reproduce the reference PCG
implementation (Bertout & Richard) segment by segment.

Skipped unless the reference package `pcg` is importable, e.g.
    PYTHONPATH=/path/to/pcg-main/src:/path/to/pcg-main pytest tests/oracle
(the reference needs matplotlib and pplpy installed).
"""

import random
from fractions import Fraction as F

import pytest

ref = pytest.importorskip("pcg.rt_sim")
from pcg.budget import proportional  # noqa: E402
from pcg.rt_models import Task as RefTask  # noqa: E402
from pcg.scheduler import pcg_star as ref_pcg_star  # noqa: E402

from unifsim.engine import simulate  # noqa: E402
from unifsim.model import Platform, Task, System  # noqa: E402
from unifsim.schedulers.dpfair import PCGStar  # noqa: E402
from unifsim.schedulers.dpfair.local import pcg_star  # noqa: E402
from unifsim.validate import validate  # noqa: E402

PERIODS = [2, 3, 4, 5, 6, 10, 12]


def _ours(tasks, speeds):
    ts = System(tuple(Task(i, C, T) for i, (C, T) in enumerate(tasks)), Platform(tuple(speeds)))
    tr = simulate(ts, PCGStar())
    validate(ts, tr)
    return ts, {(s.proc, s.job.task_id, s.job.k, s.start, s.end) for s in tr.segments}


def _reference(tasks, speeds):
    rtasks = [RefTask(task_id=i, wcet=F(C), period=T, deadline=T) for i, (C, T) in enumerate(tasks)]
    sched = ref.simulate(rtasks, list(speeds), None, budget_policy=proportional)
    return {(p, tid, k, F(s), F(e)) for p, proc in enumerate(sched) for (tid, k), (s, e) in proc}


def _random_instance(rng):
    m = rng.randint(2, 5)
    speeds = sorted([1] + [rng.randint(1, 8) for _ in range(m - 1)], reverse=True)
    n = rng.randint(1, 3 * m)
    S = sum(speeds)
    for _ in range(100):
        load = F(rng.randint(1, 20), 20)             # U / S_m in (0, 1]
        w = [rng.randint(1, 30) for _ in range(n)]
        u = [load * S * wi / sum(w) for wi in w]
        tasks = [(ui * T, T) for ui, T in zip(u, (rng.choice(PERIODS) for _ in u))]
        ts = System(tuple(Task(i, C, T) for i, (C, T) in enumerate(tasks)), Platform(tuple(speeds)))
        if ts.horvath_feasible():
            return tasks, speeds
    pytest.skip("no feasible instance drawn")


PAPER = {
    # tests/test_cases/rt_instances.py and rtns.py of the reference repository
    "exemple1": ([(33, 8), (5, 2), (7, 4), (9, 8), (4, 8), (3, 8)], [6, 3, 2, 2, 1]),
    "exemple2": ([(26, 4), (12, 2), (153, 50), (64, 100), (27, 50), (1, 25)], [8, 7, 6, 2, 1]),
    "dpfair": ([(15, 20), (25, 30), (85, 60)], [2, 1]),
}


@pytest.mark.parametrize("name", sorted(PAPER))
def test_paper_instances(name):
    tasks, speeds = PAPER[name]
    _, ours = _ours(tasks, speeds)
    assert ours == _reference(tasks, speeds)


@pytest.mark.parametrize("seed", range(150))
def test_random_instances(seed):
    tasks, speeds = _random_instance(random.Random(seed))
    _, ours = _ours(tasks, speeds)
    assert ours == _reference(tasks, speeds)


@pytest.mark.parametrize("seed", range(300))
def test_local_scheduler(seed):
    rng = random.Random(10_000 + seed)
    m = rng.randint(1, 6)
    speeds = sorted([1] + [rng.randint(1, 10) for _ in range(m - 1)], reverse=True)
    n = rng.randint(1, 10)
    budgets = [F(rng.randint(1, 400), rng.randint(1, 20)) for _ in range(n)]
    # window = minimal makespan on the uniform platform (the hardest case),
    # sometimes enlarged to leave slack
    b = sorted(budgets, reverse=True)
    prefixes = [sum(b[:k]) / sum(speeds[:k]) for k in range(1, min(m - 1, n) + 1)]
    window = max(prefixes + [sum(b) / sum(speeds[:min(m, n)])])
    window *= rng.choice([F(1), F(1), F(11, 10), F(3, 2)])
    assert pcg_star(budgets, speeds, window) == ref_pcg_star(budgets[:], speeds[:], window)
