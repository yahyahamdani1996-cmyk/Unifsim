from fractions import Fraction as F

from unifsim.schedulers.dp.local.pcg_star_v2 import pcg_star_v2


def test_martel():
    """Martel example, Table 1 / Fig. 4 of the ECRTS paper: 5 preemptions."""
    schedule = pcg_star_v2([28, 20, 16, 5, F(7, 2), F(5, 2)], (10, 8, 4, 2, 1), 3)
    assert schedule == [
        [(0, (0, 2)), (2, (2, F(14, 5))), (3, (F(14, 5), 3))],
        [(1, (0, 2)), (0, (2, 3))],
        [(2, (0, 2)), (1, (2, 3))],
        [(3, (0, F(3, 2))), (4, (F(3, 2), 3))],
        [(4, (0, F(1, 2))), (5, (F(1, 2), 3))],
    ]


def test_horvath_table3():
    """Table 3 / Fig. 3 of the ECRTS paper, plane of length C_max = 37/5."""
    schedule = pcg_star_v2([20, 19, 18, 17, 2], (4, 3, 2, 1, 1), F(37, 5))
    assert schedule == [
        [(0, (0, F(13, 5))), (2, (F(13, 5), F(79, 15))), (1, (F(79, 15), F(37, 5)))],
        [(1, (0, F(13, 5))), (3, (F(13, 5), F(37, 5)))],
        [(2, (0, F(13, 5))), (0, (F(13, 5), F(37, 5)))],
        [(3, (0, F(13, 5))), (1, (F(13, 5), F(79, 15))), (2, (F(79, 15), F(37, 5)))],
        [(4, (0, 2))],
    ]


def test_initial_c_event_on_own_processor():
    """Job 0 has exactly the capacity of pi_1 at t = 0: pinned in place, no move."""
    schedule = pcg_star_v2([30, 2], (10, 1), 3)
    assert schedule == [[(0, (0, 3))], [(1, (0, 2))]]
