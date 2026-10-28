import csv
import json
from collections import Counter

import pytest

from unifsim.campaign import SpecError, parse, run_campaign
from unifsim.campaign.report import summarize, write_report
from unifsim.cli import main
from unifsim.model.system import System

SPEC = """
name       = "t"
schedulers = ["pcg_star", "g_edf"]
count      = 3
seed       = 7
[grid]
n        = [4, 6]
platform = "4,2,1"
U        = "4-6/2"
"""


def rows(folder):
    with open(folder / "rows.csv", newline="") as f:
        return list(csv.DictReader(f))


def write(tmp_path, text, name="spec.toml"):
    p = tmp_path / name
    p.write_text(text)
    return p


# ------------------------------------------------------------------ spec
def test_points_like_gen():
    spec = parse(SPEC)
    assert [p.name for p in spec.points] == ["m3_n4_U4", "m3_n4_U6", "m3_n6_U4", "m3_n6_U6"]
    assert spec.schedulers == ["pcg_star", "g_edf"] and spec.count == 3


@pytest.mark.parametrize("bad, msg", [
    (SPEC.replace('name       = "t"', ""), "name"),
    (SPEC.replace('"g_edf"', '"nope"'), "unknown scheduler"),
    (SPEC.replace('U        = "4-6/2"', 'U = "4"\nload = 0.5'), "exactly one of U or load"),
    (SPEC.replace('platform = "4,2,1"', 'platform = "4,2,1"\nm = 3'), "exactly one of platform"),
    (SPEC + '\n[simulation]\narrivals = "sporadic"\n', "only \"periodic\""),
    (SPEC + '\nfoo = 1\n', "unknown key"),
])
def test_spec_errors(bad, msg):
    with pytest.raises(SpecError, match=msg):
        parse(bad)


def test_random_platform_points():
    spec = parse('name="r"\nschedulers=["pcg_star"]\n[grid]\nn=5\nm=[2,4]\nspeeds="1-6"\nload="0.5-1/0.5"\n')
    assert [p.name for p in spec.points] == ["m2_n5_load0.5", "m2_n5_load1", "m4_n5_load0.5", "m4_n5_load1"]
    assert spec.points[0].gen["speed_range"] == (1, 6)


# ------------------------------------------------------------------ run
def test_run_rows_success_and_failures(tmp_path):
    folder = run_campaign(write(tmp_path, SPEC), out=tmp_path / "results", jobs=1, quiet=True)
    rs = rows(folder)
    assert len(rs) == 4 * 3 * 2
    assert {r["status"] for r in rs if r["scheduler"] == "pcg_star"} == {"ok"}        # optimal
    assert all(r["success"] == ("1" if r["status"] == "ok" else "0") for r in rs)
    assert all(r["feasible"] == "1" for r in rs)
    assert any(r["status"] == "deadline_miss" for r in rs)                           # g_edf misses one
    ok = [r for r in rs if r["success"] == "1"]
    assert all(r["total_job_preemptions"] != "" and r["schedule_hash"] for r in ok)
    for r in rs:
        if r["status"] == "deadline_miss":
            assert r["miss_time"] and r["miss_job"]
            f = folder / "failures" / f"{r['point']}_ts{int(r['index']):04d}_{r['scheduler']}.json"
            s = System.load(f)                                   # replayable
            assert s.hash == r["system_hash"] and s.meta["failure"]["status"] == "deadline_miss"
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["sessions"][0]["sets_to_run"] == 12


def test_same_sets_as_gen(tmp_path):
    folder = run_campaign(write(tmp_path, SPEC), out=tmp_path / "results", jobs=1, quiet=True)
    assert main(["gen", "--platform", "4,2,1", "--n", "6", "--U", "6", "--count", "3", "--seed", "7",
                 "--out", str(tmp_path / "ts"), "--jobs", "1"]) == 0
    gen_hashes = {System.load(f).hash for f in (tmp_path / "ts" / "m3_n6_U6").glob("ts_*.json")}
    camp_hashes = {r["system_hash"] for r in rows(folder) if r["point"] == "m3_n6_U6"}
    assert gen_hashes == camp_hashes


def test_resume_and_extend(tmp_path):
    spec = write(tmp_path, SPEC)
    out = tmp_path / "results"
    folder = run_campaign(spec, out=out, jobs=1, quiet=True)
    run_campaign(spec, out=out, jobs=1, quiet=True)                       # nothing to do
    assert len(rows(folder)) == 24
    write(tmp_path, SPEC.replace("count      = 3", "count      = 4").replace('"g_edf"]', '"g_edf", "pcg_star_v2"]'))
    run_campaign(spec, out=out, jobs=1, quiet=True)
    rs = rows(folder)
    keys = Counter((r["point"], r["index"], r["scheduler"]) for r in rs)
    assert max(keys.values()) == 1 and len(rs) == 4 * 4 * 3                # no duplicate, all done
    write(tmp_path, SPEC.replace("seed       = 7", "seed       = 8"))
    with pytest.raises(SpecError, match="spec changed"):
        run_campaign(spec, out=out, jobs=1, quiet=True)
    run_campaign(spec, out=out, jobs=1, quiet=True, restart=True)
    assert len(rows(folder)) == 24


def test_parallel_equals_sequential(tmp_path):
    a = run_campaign(write(tmp_path, SPEC), out=tmp_path / "a", jobs=1, quiet=True)
    b = run_campaign(write(tmp_path, SPEC), out=tmp_path / "b", jobs=2, quiet=True)
    strip = lambda rs: sorted((r["point"], r["index"], r["scheduler"], r["status"], r["schedule_hash"]) for r in rs)  # noqa: E731
    assert strip(rows(a)) == strip(rows(b))


def test_generation_error_rows(tmp_path):
    spec = 'name="g"\nschedulers=["pcg_star"]\ncount=2\n[grid]\nn=2\nplatform="2,1"\nU=3\n[generator]\nu_max="1/2"\n'
    folder = run_campaign(write(tmp_path, spec), out=tmp_path / "r", jobs=1, quiet=True)
    rs = rows(folder)
    assert [r["status"] for r in rs] == ["generation_error"] * 2 and all(r["success"] == "" for r in rs)


def test_tasksets_from_gen_folder(tmp_path):
    assert main(["gen", "--platform", "4,2,1", "--n", "5", "--U", "5", "--count", "2",
                 "--out", str(tmp_path / "ts"), "--jobs", "1"]) == 0
    spec = f'name="f"\nschedulers=["pcg_star"]\ncount=10\ntasksets="{tmp_path / "ts"}"\n'
    folder = run_campaign(write(tmp_path, spec), out=tmp_path / "r", jobs=1, quiet=True)
    rs = rows(folder)
    assert [(r["point"], r["index"], r["status"]) for r in rs] == [("m3_n5_U5", "0", "ok"), ("m3_n5_U5", "1", "ok")]


# ------------------------------------------------------------------ report and CLI
def test_report(tmp_path):
    folder = run_campaign(write(tmp_path, SPEC), out=tmp_path / "results", jobs=1, quiet=True)
    S = summarize(folder)
    assert S["schedulers"] == ["pcg_star", "g_edf"]
    assert S["cell"]["m3_n4_U4", "pcg_star"]["success"] == 1.0
    page = write_report(folder).read_text()
    assert "Success ratio" in page and "g_edf vs pcg_star" in page and "<svg" in page


def test_cli(tmp_path, capsys):
    spec = write(tmp_path, SPEC)
    assert main(["campaign", str(spec), "--out", str(tmp_path / "res"), "--jobs", "1"]) == 0
    assert "done: 24 runs" in capsys.readouterr().out
    assert main(["campaign", "report", str(tmp_path / "res" / "t"), "--no-open"]) == 0
    assert (tmp_path / "res" / "t" / "report.html").exists()


def test_report_x_axis(tmp_path):
    folder = run_campaign(write(tmp_path, SPEC), out=tmp_path / "results", jobs=1, quiet=True)
    auto = summarize(folder)["axes"]                     # U varies: x = U, groups by n
    assert auto["m3_n4_U6"][:3] == ("n = 4, m = 3", "U", 6.0)
    by_n = summarize(folder, x="n")["axes"]              # x = n, groups by U
    assert by_n["m3_n6_U4"][:3] == ("m = 3, U = 4", "n", 6.0)
    with pytest.raises(ValueError, match="varies U, not load"):
        summarize(folder, x="load")
    one_u = SPEC.replace('U        = "4-6/2"', "U = 4").replace('name       = "t"', 'name = "u"')
    folder = run_campaign(write(tmp_path, one_u), out=tmp_path / "results", jobs=1, quiet=True)
    assert summarize(folder)["axes"]["m3_n6_U4"][1] == "n"            # only n varies: auto picks n
    assert "<svg" in write_report(folder).read_text()
