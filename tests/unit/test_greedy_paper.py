from fractions import Fraction as F

import pytest

from unifsim import Platform, System, Task, run
from unifsim.gen.bank import regenerate
from unifsim.schedulers.dp.budgets import greedy_paper, greedy_wk
from unifsim.schedulers.dp.pcg_star_v2 import PCGStarV2
from unifsim.schedulers.registry import make

EXAMPLE = System(tasks=(Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4),
                        Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
                 platform=Platform((6, 3, 2, 2, 1)))


def _compare(order, seen):
    wk, paper = greedy_wk(order), greedy_paper(order)

    def policy(jobs, plane, scheduler, view):
        a, b = wk(jobs, plane, scheduler, view), paper(jobs, plane, scheduler, view)
        seen.append((sum(a), sum(b)))
        return b
    return policy


@pytest.mark.parametrize("order", ["remaining", "index"])
def test_same_total_as_greedy_wk(order):
    systems = [EXAMPLE] + [regenerate(n, U=F(U), index=i, master_seed=3,
                                      platform=Platform((8, 6, 5, 4, 3, 2, 1, 1)),
                                      periods=(2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60))
                           for n in (6, 16) for U in (8, 20) for i in range(2)]
    seen = []
    for system in systems:
        s = PCGStarV2(budget=_compare(order, seen))
        s.name = "x"
        run(system, s)                              # raises on a miss or an invalid schedule
    assert seen and all(a == b for a, b in seen)    # both optimal: same total budget per plane


def test_registry():
    for name in ("wc_pcg_star_paper", "wc_pcg_star_v2_paper"):
        assert make(name).name == name
        run(EXAMPLE, make(name))


def test_bad_order():
    with pytest.raises(ValueError):
        greedy_paper("nope")
