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
    assert main(["gen", "--n", "8", "--U", "6", "--count", "3", "--out", str(tmp_path), "--jobs", "1"]) == 0
    files = sorted((tmp_path / "n8_U6").glob("ts_*.json"))
    assert [f.name for f in files] == ["ts_0000.json", "ts_0001.json", "ts_0002.json"]
    s = System.load(files[1])
    u = [t.u for t in s.tasks]
    assert s.U == 6 and u == sorted(u, reverse=True) and s.horvath_feasible()
    before = files[1].read_text()
    main(["gen", "--n", "8", "--U", "6", "--count", "3", "--out", str(tmp_path), "--jobs", "1"])   # resume
    assert files[1].read_text() == before
    main(["gen", "--n", "8", "--U", "6", "--index", "1", "--out", str(tmp_path / "one"), "--jobs", "1"])
    assert (tmp_path / "one" / "n8_U6" / "ts_0001.json").read_text() == before   # same set alone


def test_gen_bank_matches_files(tmp_path):
    main(["gen", "--n", "8", "--U", "6", "--count", "2", "--out", str(tmp_path), "--jobs", "1"])
    main(["gen", "--n", "8", "--U", "6", "--count", "2", "--bank", "--out", str(tmp_path / "b"), "--jobs", "1"])
    bank = [s.hash for s in read_bank(tmp_path / "b" / "n8_U6.jsonl.gz")]
    files = [System.load(tmp_path / "n8_U6" / f"ts_{i:04d}.json").hash for i in range(2)]
    assert bank == files
