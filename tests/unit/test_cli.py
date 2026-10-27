from fractions import Fraction as F

import pytest

pytest.importorskip("convolutionalfixedsum")

from unifsim import System  # noqa: E402
from unifsim.cli import main, values  # noqa: E402
from unifsim.gen import read_bank  # noqa: E402


def test_values():
    assert values("20") == [20]
    assert values("8-20/4") == [8, 12, 16, 20]
    assert values("6-8,10") == [6, 7, 8, 10]
    assert [str(v) for v in values("7/2")] == ["7/2"]


def test_gen_files_resume_and_index(tmp_path):
    assert main(["gen", "--platform", "8,6,5,4,3,2,1,1", "--n", "8", "--U", "6", "--count", "3", "--out", str(tmp_path), "--jobs", "1"]) == 0
    files = sorted((tmp_path / "m8_n8_U6").glob("ts_*.json"))
    assert [f.name for f in files] == ["ts_0000.json", "ts_0001.json", "ts_0002.json"]
    s = System.load(files[1])
    u = [t.u for t in s.tasks]
    assert s.U == 6 and u == sorted(u, reverse=True) and s.horvath_feasible()
    before = files[1].read_text()
    main(["gen", "--platform", "8,6,5,4,3,2,1,1", "--n", "8", "--U", "6", "--count", "3", "--out", str(tmp_path), "--jobs", "1"])   # resume
    assert files[1].read_text() == before
    main(["gen", "--platform", "8,6,5,4,3,2,1,1", "--n", "8", "--U", "6", "--index", "1", "--out", str(tmp_path / "one"), "--jobs", "1"])
    assert (tmp_path / "one" / "m8_n8_U6" / "ts_0001.json").read_text() == before   # same set alone


def test_gen_bank_matches_files(tmp_path):
    main(["gen", "--platform", "8,6,5,4,3,2,1,1", "--n", "8", "--U", "6", "--count", "2", "--out", str(tmp_path), "--jobs", "1"])
    main(["gen", "--platform", "8,6,5,4,3,2,1,1", "--n", "8", "--U", "6", "--count", "2", "--bank", "--out", str(tmp_path / "b"), "--jobs", "1"])
    bank = [s.hash for s in read_bank(tmp_path / "b" / "m8_n8_U6.jsonl.gz")]
    files = [System.load(tmp_path / "m8_n8_U6" / f"ts_{i:04d}.json").hash for i in range(2)]
    assert bank == files


def test_gen_random_platform(tmp_path):
    main(["gen", "--m", "5", "--n", "10", "--load", "0.67", "--count", "4", "--out", str(tmp_path), "--jobs", "1"])
    sets = [System.load(f) for f in sorted((tmp_path / "m5_n10_load0.67").glob("ts_*.json"))]
    assert len(sets) == 4
    assert len({s.platform.speeds for s in sets}) > 1                   # a platform drawn per set
    for s in sets:
        sp = s.platform.speeds
        assert len(sp) == 5 and sp[-1] == 1 and list(sp) == sorted(sp, reverse=True)
        assert all(x.denominator == 1 and 1 <= x <= 10 for x in sp)
        assert s.U == F(67, 100) * sum(sp) and s.horvath_feasible()
        assert s.meta["platform_mode"] == "random"


@pytest.mark.parametrize("args", [
    ["--n", "8", "--U", "6"],                                   # no platform
    ["--m", "4", "--platform", "2,1", "--n", "8", "--load", "0.5"],   # both platforms
    ["--m", "4", "--n", "8", "--U", "6"],                       # U with a random platform
    ["--platform", "2,1", "--n", "8"],                          # no utilization
])
def test_gen_bad_arguments(tmp_path, args):
    with pytest.raises(SystemExit):
        main(["gen", *args, "--out", str(tmp_path), "--jobs", "1"])


def _gen_file(tmp_path):
    main(["gen", "--platform", "6,3,2,2,1", "--n", "6", "--U", "10", "--out", str(tmp_path), "--jobs", "1"])
    return tmp_path / "m5_n6_U10" / "ts_0000.json"


def test_simulate_file_and_generator_options_are_the_same_system(tmp_path, capsys):
    f = _gen_file(tmp_path)
    assert main(["simulate", str(f), "--scheduler", "pcg_star", "--json", str(tmp_path / "a.json")]) == 0
    assert main(["simulate", "--platform", "6,3,2,2,1", "--n", "6", "--U", "10", "--scheduler", "pcg_star",
                 "--json", str(tmp_path / "b.json")]) == 0
    import json
    a, b = (json.loads((tmp_path / x).read_text()) for x in ("a.json", "b.json"))
    assert a["hash"] == b["hash"] and a["metrics"] == b["metrics"] and a["status"] == "ok"
    assert "VALID" in capsys.readouterr().out


def test_simulate_failure_exit_code(tmp_path, capsys):
    assert main(["simulate", "--platform", "2,1", "--n", "3", "--U", "3", "--scheduler", "g_edf"]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_simulate_random_platform_and_schedule(capsys):
    assert main(["simulate", "--m", "4", "--n", "6", "--load", "0.8", "--index", "2",
                 "--scheduler", "wc_pcg_star", "--schedule"]) == 0
    out = capsys.readouterr().out
    assert "VALID" in out and "P0 " in out


@pytest.mark.parametrize("args", [
    ["simulate", "--scheduler", "pcg_star"],                                     # no system
    ["simulate", "--platform", "2,1", "--n", "4", "--U", "1-3", "--scheduler", "pcg_star"],   # ranges
])
def test_simulate_bad_arguments(args):
    with pytest.raises(SystemExit):
        main(args)


def test_simulate_refuses_folder(tmp_path):
    f = _gen_file(tmp_path)
    with pytest.raises(SystemExit):
        main(["simulate", str(f.parent), "--scheduler", "pcg_star"])


def test_compare_writes_report(tmp_path, capsys):
    f = _gen_file(tmp_path)
    out = tmp_path / "r.html"
    assert main(["compare", str(f), "--schedulers", "pcg_star,wc_pcg_star,g_edf", "--out", str(out), "--no-open"]) == 0
    text = capsys.readouterr().out
    assert out.exists() and "wc_pcg_star" in text and "Job preemptions" in text


def test_list(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "pcg_star" in out and "wc_pcg_star" in out and "g_edf" in out
