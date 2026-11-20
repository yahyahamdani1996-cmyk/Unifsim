"""groups generator (Sec. 7.2) and sporadic campaigns."""

import csv
from fractions import Fraction as F

import pytest

from unifsim.campaign import run_campaign
from unifsim.campaign.spec import SpecError, parse
from unifsim.gen import regenerate

SPEC = """
name = "sporadic_small"
schedulers = ["pcg_star_v2", "pcg_star_v2_dyn"]
count = 2
[grid]
n = 6
m = 3
load = 0.7
[generator]
kind = "groups"
period_range = "10-30"
[simulation]
arrivals = "sporadic"
alpha = [0, 1]
horizon = "3*Tmax"
"""


def test_groups_generator():
    for i in range(20):
        s = regenerate(20, index=i, generator="groups", m=8, speed_range=(1, 10), load=F(7, 10),
                       period_range=(10, 100))
        assert s.U == F(7, 10) * sum(s.platform.speeds)
        assert all(10 <= t.T <= 100 and t.T == int(t.T) for t in s.tasks)
        assert s.horvath_feasible()
    a = regenerate(20, index=3, generator="groups", m=8, load=F(7, 10), period_range=(10, 100))
    b = regenerate(20, index=3, generator="groups", m=8, load=F(7, 10), period_range=(10, 100))
    assert a.hash == b.hash


def test_spec_alpha_points():
    spec = parse(SPEC)
    assert [p.name for p in spec.points] == ["m3_n6_load0.7_alpha0", "m3_n6_load0.7_alpha1"]
    assert [p.alpha for p in spec.points] == [0, 1]
    assert spec.points[0].gen == spec.points[1].gen          # same sets for every alpha


@pytest.mark.parametrize("bad", [
    SPEC.replace('arrivals = "sporadic"', 'arrivals = "periodic"'),                # alpha without sporadic
    SPEC.replace('alpha = [0, 1]\n', ''),                                         # sporadic without alpha
    SPEC.replace('horizon = "3*Tmax"', 'horizon = "3*H"'),
    SPEC.replace('kind = "groups"', 'kind = "cfs_uniform"'),                      # period_range needs groups
])
def test_spec_errors(bad):
    with pytest.raises(SpecError):
        parse(bad)


def test_sporadic_campaign_runs(tmp_path):
    path = tmp_path / "spec.toml"
    path.write_text(SPEC)
    run_campaign(path, out=tmp_path / "results", jobs=1, quiet=True)
    rows = list(csv.DictReader(open(tmp_path / "results" / "sporadic_small" / "rows.csv")))
    assert len(rows) == 2 * 2 * 2 and {r["status"] for r in rows} == {"ok"}
    assert {r["alpha"] for r in rows} == {"0", "1"}
    # the same set for both alphas (paired), and planes are recorded
    by = {(r["alpha"], r["index"], r["scheduler"]): r for r in rows}
    assert by["0", "0", "pcg_star_v2"]["system_hash"] == by["1", "0", "pcg_star_v2"]["system_hash"]
    assert all(int(r["tl_planes"]) > 0 for r in rows)
