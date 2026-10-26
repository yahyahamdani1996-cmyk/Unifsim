"""Each invariant must reject a trace corrupted on purpose."""

from dataclasses import replace
from fractions import Fraction as F

import pytest

from pcgsim.engine import simulate
from pcgsim.model import Job, Platform, Task, TaskSet
from pcgsim.schedulers.global_ import GEDF
from pcgsim.trace import Segment, Trace
from pcgsim.validate import ValidationError, validate

TS = TaskSet((Task(0, 2, 4), Task(1, 3, 6)), Platform((2, 1)))
J0 = Job.of(TS.task(0), 0)   # [0, 4), C = 2
J1 = Job.of(TS.task(0), 1)   # [4, 8), C = 2
K0 = Job.of(TS.task(1), 0)   # [0, 6), C = 3
K1 = Job.of(TS.task(1), 1)   # [6, 12), C = 3


def _trace(segs):
    tr = Trace(m=2, horizon=F(12))
    tr.segments = [Segment(*s) for s in segs]
    return tr


# J0: 2 units on P0 (speed 2) -> 1 time unit ; K0: 3 units on P1 (speed 1) -> 3 time units
GOOD = [
    (0, J0, F(0), F(1)), (1, K0, F(0), F(3)),
    (0, J1, F(4), F(5)), (0, K1, F(6), F(7) + F(1, 2)),
    (0, Job.of(TS.task(0), 2), F(8), F(9)),
]


def test_good_trace_passes():
    validate(TS, _trace(GOOD))
    validate(TS, simulate(TS, GEDF()))


def _expect(code, segs):
    with pytest.raises(ValidationError) as e:
        validate(TS, _trace(segs))
    assert e.value.code == code, str(e.value)


def test_V0_unknown_job():
    _expect("V0", GOOD + [(1, Job.of(TS.task(0), 7), F(10), F(11))])


def test_V1_beyond_horizon():
    segs = GOOD[:-1] + [(0, Job.of(TS.task(0), 2), F(8), F(13))]
    _expect("V1", segs)


def test_V2_overlap_on_processor():
    segs = [(0, J0, F(0), F(1)), (0, K0, F(1, 2), F(2)), (1, K0, F(2), F(3) + F(1, 2))] + GOOD[2:]
    # K0 also overlaps itself? no: [1/2,2) on P0 and [2,7/2) on P1 are disjoint
    _expect("V2", segs)


def test_V3_job_in_parallel():
    segs = [(0, J0, F(0), F(1, 2)), (1, J0, F(0), F(1)), (1, K0, F(1), F(4))] + GOOD[2:]
    _expect("V3", segs)


def test_V4_before_release():
    segs = GOOD[:2] + [(0, J1, F(3), F(4))] + GOOD[3:]
    _expect("V4", segs)


def test_V5_wrong_work():
    # the case correct_schedule lets through in the original code: too little work
    segs = [(0, J0, F(0), F(1, 2))] + GOOD[1:]
    _expect("V5", segs)


def test_V6_after_deadline():
    segs = [(0, J0, F(0), F(1, 2)), (0, J0, F(9, 2), F(5))] + GOOD[1:2] + [(0, J1, F(5), F(6))] + GOOD[3:]
    # J0 fails V4? no: J0 starts at 0 >= release 0. Its last segment ends at 5 > deadline 4
    _expect("V6", segs)


def test_V7_missing_job():
    _expect("V7", GOOD[:-1])
