from fractions import Fraction as F

from unifsim.engine import simulate
from unifsim.metrics import compute_metrics
from unifsim.model import Job, Platform, System, Task
from unifsim.schedulers.registry import make
from unifsim.trace import PlaneRecord, Segment, Trace

SYS = System((Task(0, 4, 8), Task(1, 2, 8)), Platform((2, 1)))
A0 = Job.of(SYS.task(0), 0)   # C = 4, [0, 8)
B0 = Job.of(SYS.task(1), 0)   # C = 2, [0, 8)


def _trace(segs, planes=()):
    tr = Trace(m=2, horizon=F(8), meta={"scheduler": "hand"})
    tr.segments = [Segment(*s) for s in segs]
    tr.planes = [PlaneRecord(F(a), F(b), ()) for a, b in planes]
    return tr


def test_one_preemption_one_migration():
    # A0 runs on P0 [0,1) (2 units), stops, resumes on P1 [3,5) (2 units)
    m = compute_metrics(SYS, _trace([(0, A0, F(0), F(1)), (1, A0, F(3), F(5)), (0, B0, F(1), F(2))]))
    assert m.per_job[A0] == (1, 1) and m.per_job[B0] == (0, 0)
    assert (m.total_job_preemptions, m.total_job_migrations) == (1, 1)
    assert m.local_job_preemptions is None          # no TL-planes recorded


def test_preemption_without_migration():
    # A0 on P0 [0,1) then P0 again [2,3): preempted, same processor
    m = compute_metrics(SYS, _trace([(0, A0, F(0), F(1)), (0, A0, F(2), F(3)), (1, B0, F(0), F(2))]))
    assert m.per_job[A0] == (1, 0)


def test_migration_without_gap():
    # A0 on P1 [0,1) then directly on P0 [1, 3/2): one preemption and one migration
    m = compute_metrics(SYS, _trace([(1, A0, F(0), F(1)), (0, A0, F(1), F(5, 2)), (1, B0, F(1), F(3))]))
    assert m.per_job[A0] == (1, 1)


def test_local_and_boundary():
    planes = [(0, 4), (4, 8)]
    # A0: P0 [0,1) and P1 [2,3) in plane 0 (local), then P0 [4, 9/2) in plane 1 (boundary)
    segs = [(0, A0, F(0), F(1)), (1, A0, F(2), F(3)), (0, A0, F(4), F(9, 2)), (1, B0, F(5), F(7))]
    m = compute_metrics(SYS, _trace(segs, planes))
    assert (m.total_job_preemptions, m.local_job_preemptions, m.boundary_job_preemptions) == (2, 1, 1)
    assert (m.total_job_migrations, m.local_job_migrations, m.boundary_job_migrations) == (2, 1, 1)


def test_continuous_across_boundary_is_not_a_preemption():
    planes = [(0, 4), (4, 8)]
    m = compute_metrics(SYS, _trace([(1, A0, F(2), F(6)), (0, B0, F(0), F(1))], planes))
    assert m.total_job_preemptions == 0 and m.local_job_preemptions == 0


def test_response_times():
    # A0 completes at 5 (ratio 5/8), B0 at 2 (ratio 2/8)
    m = compute_metrics(SYS, _trace([(0, A0, F(0), F(1)), (1, A0, F(3), F(5)), (0, B0, F(1), F(2))]))
    assert m.avg_response_time_ratio == F(7, 16)
    assert (m.worst_response_time_ratio, m.best_response_time_ratio) == (F(5, 8), F(1, 4))
    assert m.n_jobs_completed == 2


def test_running_example_matches_shrimp():
    """Running example (paper Tables 2 and 3), values logged by shrimp for PCG*."""
    s = System((Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4), Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
               Platform((6, 3, 2, 2, 1)))
    m = compute_metrics(s, simulate(s, make("pcg_star")))
    assert (m.local_job_preemptions, m.boundary_job_preemptions) == (24, 14)
    assert (m.local_job_migrations, m.boundary_job_migrations) == (24, 11)
    assert (m.total_job_preemptions, m.total_job_migrations) == (38, 35)
    assert (m.total_task_migrations, m.total_boundary_task_migrations) == (39, 4)
    assert m.n_jobs_completed == 10
    assert round(float(m.avg_response_time_ratio), 4) == 0.9266
    assert (m.worst_response_time_ratio, m.best_response_time_ratio) == (1, F(25, 32))
    assert all(pre <= 2 * (5 - 1) for _, _, pre in m.per_plane_preemptions)   # Thm. 6
