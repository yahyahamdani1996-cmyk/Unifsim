from unifsim.gui import compare, run
from unifsim.model import Platform, System, Task


def test_compare_writes_report(tmp_path):
    s = System((Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4), Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
               Platform((6, 3, 2, 2, 1)))
    page = compare(s, ["pcg_star", "g_edf"], tmp_path / "r.html").read_text()
    assert "pcg_star" in page and "g_edf" in page and page.count("<svg") == 2


def test_failure_is_reported_not_raised(tmp_path):
    s = System((Task(0, 3, 2), Task(1, 2, 3), Task(2, 5, 6)), Platform((2, 1)))   # G-EDF misses here
    assert run(s, "g_edf")["error"].startswith("DeadlineMiss")
    page = compare(s, ["pcg_star", "g_edf"], tmp_path / "r.html").read_text()
    assert "failed" in page and page.count("<svg") == 1
