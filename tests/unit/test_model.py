from fractions import Fraction as F

import pytest

from unifsim.model import Job, Platform, Task, System


def test_task_rejects_float():
    with pytest.raises(TypeError):
        Task(0, 1.5, 4)


def test_task_invariants():
    with pytest.raises(ValueError):
        Task(0, 0, 4)            # C = 0
    with pytest.raises(ValueError):
        Task(0, 1, 4, D=5)       # D > T
    with pytest.raises(ValueError):
        Task(0, 1, F(9, 2))      # non-integer period
    t = Task(0, "7/2", 4)
    assert t.C == F(7, 2) and t.D == 4 and t.u == F(7, 8) and t.implicit
    assert Task(1, 3, 2).u == F(3, 2)   # u > 1 is valid on a uniform platform


def test_job_of():
    j = Job.of(Task(3, 2, 5, D=4), 2)
    assert (j.release, j.deadline, j.C, j.name) == (10, 14, 2, "T3_2")


def test_platform_sorted_and_positive():
    with pytest.raises(ValueError):
        Platform((1, 2))
    with pytest.raises(ValueError):
        Platform((2, 0))
    with pytest.raises(TypeError):
        Platform((2.0, 1))
    p = Platform((6, 3, 2, 2, 1))
    assert p.m == 5 and p.S(0) == 0 and p.S(2) == 9 and p.S(5) == 14


def _ts():
    return System((Task(0, 3, 2), Task(1, 2, 3), Task(2, 5, 6)), Platform((2, 1)))


def test_hyperperiod_and_jobs():
    ts = _ts()
    assert ts.hyperperiod == 6
    jobs = ts.jobs(6)
    assert len(jobs) == 3 + 2 + 1
    assert [j.release for j in jobs] == sorted(j.release for j in jobs)


def test_json_roundtrip_and_hash():
    ts = _ts()
    back = System.from_json(ts.to_json())
    assert back == ts and back.hash == ts.hash
    reordered = System(tuple(reversed(ts.tasks)), ts.platform)
    assert reordered.hash == ts.hash          # hash independent of task order
    other = System((Task(0, 3, 2), Task(1, 2, 3), Task(2, 4, 6)), ts.platform)
    assert other.hash != ts.hash


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        System((Task(0, 1, 2), Task(0, 1, 3)), Platform((1,)))


def test_horvath():
    plat = Platform((2, 1))
    # u = 3/2, 2/3, 5/6 : u_max = 3/2 <= S_1 = 2 and U = 3 = S_2 -> feasible
    assert _ts().horvath_feasible() is True
    # u_max = 5/2 > S_1 = 2 -> infeasible although U = 5/2 + 1/4 <= S_2 = 3
    assert System((Task(0, 5, 2), Task(1, 1, 4)), plat).horvath_feasible() is False
    # U = 3 + 1/4 > S_2 = 3 -> infeasible
    assert System((Task(0, 3, 2), Task(1, 7, 4)), plat).horvath_feasible() is False
    with pytest.raises(NotImplementedError):
        System((Task(0, 1, 4, D=3),), plat).horvath_feasible()
