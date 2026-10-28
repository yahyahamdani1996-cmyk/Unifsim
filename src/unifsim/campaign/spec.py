"""Campaign specification: a TOML file, validated and expanded into grid points.

See docs/CAMPAIGN_DESIGN.md. The grid uses the same options, defaults and
point names as `unifsim gen`, so a campaign point is the same set of task
sets that `unifsim gen` would write.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:          # Python 3.10
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

GEN_DEFAULTS = {
    "periods": (2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60),
    "u_min": "1/100",
    "u_max": None,
    "quantum": "1/10000",
    "rounding": "exact_sum",
    "order": "sorted",
}
TOP_KEYS = {"name", "description", "schedulers", "count", "seed", "grid", "generator", "simulation", "tasksets"}
GRID_KEYS = {"n", "platform", "m", "speeds", "U", "load"}


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class Point:
    """One grid point: a name (as `unifsim gen` folders) and the regenerate() arguments."""
    name: str
    n: int
    m: int
    kind: str                  # "U" or "load"
    value: Fraction
    gen: dict = field(compare=False, hash=False)    # regenerate(**gen, index=i)


@dataclass
class Spec:
    name: str
    schedulers: list
    count: int
    seed: int
    points: list               # [Point], empty when tasksets is given
    tasksets: Path | None
    raw: dict                  # the parsed TOML, kept for the results folder
    text: str                  # the file content, copied verbatim
    description: str = ""


def _values(x, what):
    """TOML value -> list of exact Fractions. Accepts 18, 0.5, "37/2", "6-30/2", [..]."""
    from ..cli import values
    if isinstance(x, bool):
        raise SpecError(f"{what}: {x!r} is not a number")
    if isinstance(x, list):
        return [v for item in x for v in _values(item, what)]
    if isinstance(x, (int, float)):
        return [Fraction(str(x))]          # str(): 0.1 means 1/10, not the binary float
    if isinstance(x, str):
        try:
            return values(x)
        except Exception as e:
            raise SpecError(f"{what}: cannot read {x!r} ({e})") from None
    raise SpecError(f"{what}: unsupported value {x!r}")


def _ints(x, what):
    out = []
    for v in _values(x, what):
        if v.denominator != 1 or v <= 0:
            raise SpecError(f"{what}: {v} is not a positive integer")
        out.append(int(v))
    return out


def parse(text: str, source="spec") -> Spec:
    if tomllib is None:
        raise SpecError("reading TOML needs Python >= 3.11 (or: pip install tomli)")
    try:
        d = tomllib.loads(text)
    except Exception as e:
        raise SpecError(f"{source}: invalid TOML ({e})") from None

    unknown = set(d) - TOP_KEYS
    if unknown:
        raise SpecError(f"unknown key(s) {sorted(unknown)}; allowed: {sorted(TOP_KEYS)}")
    name = d.get("name")
    if not isinstance(name, str) or not name or any(c in name for c in "/\\ "):
        raise SpecError("name: required, no spaces or slashes (it is the results folder name)")

    scheds = d.get("schedulers")
    if isinstance(scheds, str):
        scheds = [scheds]
    if not scheds or not all(isinstance(s, str) for s in scheds) or len(set(scheds)) != len(scheds):
        raise SpecError("schedulers: a non-empty list of distinct names, e.g. [\"pcg_star\", \"g_edf\"]")
    from ..schedulers.registry import REGISTRY
    bad = [s for s in scheds if s not in REGISTRY]
    if bad:
        raise SpecError(f"unknown scheduler(s) {bad}; known: {sorted(REGISTRY)}")

    count = d.get("count", 1)
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise SpecError("count: a positive integer (sets per grid point)")
    seed = d.get("seed", 2026)
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise SpecError("seed: an integer")

    sim = d.get("simulation", {})
    if set(sim) - {"arrivals", "horizon"}:
        raise SpecError(f"simulation: unknown key(s) {sorted(set(sim) - {'arrivals', 'horizon'})}")
    if sim.get("arrivals", "periodic") != "periodic":
        raise SpecError("simulation.arrivals: only \"periodic\" is implemented (key reserved for sporadic tasks)")
    if sim.get("horizon", "hyperperiod") != "hyperperiod":
        raise SpecError("simulation.horizon: only \"hyperperiod\" is implemented")

    tasksets = d.get("tasksets")
    if tasksets is not None:
        if "grid" in d or "generator" in d:
            raise SpecError("tasksets: the sets come from files, so no [grid] or [generator]")
        p = Path(tasksets)
        return Spec(name, list(scheds), count, seed, [], p, d, text, d.get("description", ""))

    points = _points(d.get("grid"), d.get("generator", {}), seed)
    return Spec(name, list(scheds), count, seed, points, None, d, text, d.get("description", ""))


def _points(grid, generator, seed):
    from ..cli import point_name, speeds as parse_speeds
    from ..model.platform import Platform

    if not isinstance(grid, dict):
        raise SpecError("[grid] is required (or give tasksets = \"folder\")")
    unknown = set(grid) - GRID_KEYS
    if unknown:
        raise SpecError(f"grid: unknown key(s) {sorted(unknown)}; allowed: {sorted(GRID_KEYS)}")
    if "n" not in grid:
        raise SpecError("grid.n is required")
    if ("platform" in grid) == ("m" in grid):
        raise SpecError("grid: give exactly one of platform (fixed) or m (random speeds)")
    if ("U" in grid) == ("load" in grid):
        raise SpecError("grid: give exactly one of U or load")
    if "m" in grid and "U" in grid:
        raise SpecError("grid: with a random platform (m), give load (U = load x S_m)")
    if "platform" in grid and "speeds" in grid:
        raise SpecError("grid.speeds is the random speed range, only with m")

    unknown = set(generator) - set(GEN_DEFAULTS)
    if unknown:
        raise SpecError(f"generator: unknown key(s) {sorted(unknown)}; allowed: {sorted(GEN_DEFAULTS)}")
    g = dict(GEN_DEFAULTS, **generator)
    periods = g["periods"]
    if isinstance(periods, str):
        periods = [p for p in periods.split(",")]
    try:
        periods = tuple(int(p) for p in periods)
    except (TypeError, ValueError):
        raise SpecError("generator.periods: a list of integers") from None
    base = dict(master_seed=seed, periods=periods, u_min=str(g["u_min"]),
                u_max=None if g["u_max"] is None else str(g["u_max"]),
                quantum=str(g["quantum"]), rounding=g["rounding"], order=g["order"])
    if base["rounding"] not in ("exact_sum", "independent"):
        raise SpecError("generator.rounding: exact_sum or independent")
    if base["order"] not in ("sorted", "random"):
        raise SpecError("generator.order: sorted or random")

    ns = _ints(grid["n"], "grid.n")
    kind = "U" if "U" in grid else "load"
    targets = _values(grid[kind], f"grid.{kind}")
    plats = []
    if "platform" in grid:
        texts = grid["platform"] if isinstance(grid["platform"], list) else [grid["platform"]]
        for t in texts:
            if not isinstance(t, str):
                raise SpecError("grid.platform: speeds as a string, e.g. \"8,6,5,4,3,2,1,1\"")
            pl = Platform(parse_speeds(t))
            plats.append((pl.m, {"platform": pl}))
    else:
        rng = grid.get("speeds", "1-10")
        try:
            lo, hi = (int(x) for x in str(rng).split("-"))
        except ValueError:
            raise SpecError("grid.speeds: an integer range lo-hi, e.g. \"1-10\"") from None
        for m in _ints(grid["m"], "grid.m"):
            plats.append((m, {"m": m, "speed_range": (lo, hi)}))

    points, seen = [], set()
    for (m, pkw), n, value in itertools.product(plats, ns, targets):
        name = point_name(m, n, kind, value)
        if "platform" in pkw and len(plats) > 1:      # several fixed platforms: make names distinct
            name = "P" + "-".join(str(s) for s in pkw["platform"].speeds) + "_" + name
        if name in seen:
            raise SpecError(f"grid: point {name} appears twice")
        seen.add(name)
        gen = dict(base, n=n, **pkw, **({"U": value} if kind == "U" else {"load": value}))
        points.append(Point(name, n, m, kind, value, gen))
    return points


def load(path) -> Spec:
    path = Path(path)
    if not path.is_file():
        raise SpecError(f"{path}: spec file not found")
    return parse(path.read_text(encoding="utf-8"), str(path))
