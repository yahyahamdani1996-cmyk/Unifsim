from fractions import Fraction as F

import pytest

pytest.importorskip("convolutionalfixedsum")

from unifsim.gen import (GenerationError, cfs_uniform, derive_seed, point,  # noqa: E402
                         read_bank, regenerate, write_bank)
from unifsim.model import Platform  # noqa: E402

P = Platform((8, 6, 5, 4, 3, 2, 1, 1))
PER = (2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60)
KW = dict(platform=P, periods=PER, u_max=8)


def test_derive_seed_stable_and_nonzero():
    assert derive_seed("a", 1, F(1, 2)) == derive_seed("a", 1, F(1, 2))   # same in every process
    assert derive_seed("a", 1) != derive_seed("a", 2)
    assert all(derive_seed(i) > 0 for i in range(1000))


def test_deterministic():
    a = cfs_uniform(12, 18, seed=42, **KW)
    b = cfs_uniform(12, 18, seed=42, **KW)
    c = cfs_uniform(12, 18, seed=43, **KW)
    assert a.hash == b.hash and a.hash != c.hash


@pytest.mark.parametrize("U", [6, 18, 30])
@pytest.mark.parametrize("n", [8, 20, 40])
def test_exact_sum_bounds_feasible(n, U):
    s = cfs_uniform(n, U, seed=n * 100 + U, **KW)
    u = [t.u for t in s.tasks]
    assert s.U == U                                          # exactly, also at U = S_m = 30
    assert all(F(1, 100) <= x <= 8 for x in u)
    assert all((x / F(1, 10000)).denominator == 1 for x in u)  # multiples of the quantum
    assert all(t.T in PER for t in s.tasks)
    assert s.horvath_feasible() and s.hyperperiod <= 60
    assert s.meta["generator"] == "cfs_uniform@1" and F(s.meta["U_reached"]) == U


def test_order_sorted_by_default_or_random():
    srt = cfs_uniform(20, 18, seed=5, **KW)
    u = [t.u for t in srt.tasks]
    assert u == sorted(u, reverse=True)                      # default, as in shrimp: task 0 = heaviest
    rnd = [cfs_uniform(20, 18, seed=k, order="random", **KW) for k in range(1, 6)]
    assert any([t.u for t in s.tasks] != sorted([t.u for t in s.tasks], reverse=True) for s in rnd)


def test_independent_rounding_is_shrimp_behaviour():
    s = cfs_uniform(40, 18, seed=9, rounding="independent", **KW)
    assert abs(s.U - 18) <= 40 * F(1, 20000)                 # sum may differ from U


def test_point_and_regenerate():
    xs = list(point(8, 12, 5, master_seed=2027, **KW))
    assert len({x.hash for x in xs}) == 5
    assert regenerate(8, 12, 3, master_seed=2027, **KW).hash == xs[3].hash   # any order, any process
    assert xs[3].meta["index"] == 3 and xs[3].meta["master_seed"] == 2027


@pytest.mark.parametrize("name", ["bank.jsonl", "bank.jsonl.gz"])
def test_bank_roundtrip(tmp_path, name):
    xs = list(point(8, 12, 4, master_seed=1, **KW))
    assert write_bank(tmp_path / name, xs) == 4
    back = list(read_bank(tmp_path / name))
    assert [b.hash for b in back] == [x.hash for x in xs] and back[0].meta == xs[0].meta


def test_bank_detects_modification(tmp_path):
    import json
    write_bank(tmp_path / "b.jsonl", point(8, 12, 1, master_seed=1, **KW))
    d = json.loads((tmp_path / "b.jsonl").read_text())
    d["tasks"][0]["C"] = "1/7"                                # edit a set by hand
    (tmp_path / "b.jsonl").write_text(json.dumps(d) + "\n")
    with pytest.raises(ValueError):
        list(read_bank(tmp_path / "b.jsonl"))


def test_impossible_target():
    with pytest.raises(GenerationError):
        cfs_uniform(4, 40, seed=1, **KW)                     # 4 tasks cannot reach U = 40 with u <= 8
