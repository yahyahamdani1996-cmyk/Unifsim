"""Generating many task sets, regenerating one, and freezing them in banks.

- point(n, U, count, master_seed, **params): the `count` sets of one campaign point,
  set i generated with seed derive_seed(master_seed, n, U, i): independent of the
  order of generation and of the number of workers;
- regenerate(n, U, index, master_seed, **params): exactly set `index` of that point;
- write_bank / read_bank: one set per line (JSONL), gzip if the name ends in .gz.
  A bank is the reference for anything published; seeds are for working.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from fractions import Fraction

from ..model.system import System
from ..model.task import exact
from .cfs_uniform import GenerationError, cfs_uniform
from .platforms import random_platform
from .seeds import derive_seed

GENERATORS = {"cfs_uniform": cfs_uniform}


def set_seed(master_seed, n, U, index) -> int:
    return derive_seed("set", master_seed, n, U, index)


def regenerate(n, U=None, index=0, master_seed=1, generator="cfs_uniform", *,
               platform=None, m=None, speed_range=(1, 10), load=None, **params) -> System:
    """Set `index` of a campaign point. Two platform modes:
      fixed : platform=Platform(...) (or speeds); U given, or load (U = load * S_m)
      random: m=..., speed_range=(lo, hi), load=...: for each set, a platform of m
              processors is drawn (integer speeds in [lo, hi], slowest = 1), then
              U = load * S_m and the tasks are drawn for that platform."""
    if (platform is None) == (m is None):
        raise ValueError("give exactly one of platform (fixed) or m (random platform)")
    if (U is None) == (load is None):
        raise ValueError("give exactly one of U or load")
    if m is not None and U is not None:
        raise ValueError("with a random platform, give load (U = load * S_m), not U")
    key = U if U is not None else f"load={exact(load, 'load')}"
    key_m = f"m={m}:{speed_range[0]}-{speed_range[1]}" if m is not None else "fixed"
    seed = set_seed(master_seed, n, f"{key}|{key_m}", index)
    if m is not None:
        platform = random_platform(m, speed_range[0], speed_range[1], derive_seed("platform", seed))
    elif not hasattr(platform, "speeds"):
        from ..model.platform import Platform
        platform = Platform(tuple(platform))
    if U is None:
        U = exact(load, "load") * sum(platform.speeds, Fraction(0))
    system = GENERATORS[generator](n=n, U=U, platform=platform, seed=seed, **params)
    system.meta.update({"master_seed": master_seed, "index": index,
                        "platform_mode": "random" if m is not None else "fixed"})
    if m is not None:
        system.meta.update({"m": m, "speed_range": list(speed_range)})
    if load is not None:
        system.meta["load"] = str(exact(load, "load"))
    return system


def point(n, U=None, count=1, master_seed=1, generator="cfs_uniform", **params):
    """Yield the `count` task sets of the campaign point (n, U) or (n, load)."""
    for i in range(count):
        yield regenerate(n, U, i, master_seed, generator, **params)


def _open(path, mode):
    path = Path(path)
    return gzip.open(path, mode + "t", encoding="utf-8") if path.suffix == ".gz" else open(path, mode, encoding="utf-8")


def write_bank(path, systems) -> int:
    """Write systems to a JSONL bank (one canonical system + meta + hash per line)."""
    k = 0
    with _open(path, "w") as f:
        for s in systems:
            d = s.canonical()
            d["meta"] = s.meta
            d["hash"] = s.hash
            f.write(json.dumps(d, sort_keys=True, separators=(",", ":")) + "\n")
            k += 1
    return k


def read_bank(path):
    """Yield the systems of a bank; checks each stored hash."""
    with _open(path, "r") as f:
        for line_no, line in enumerate(f, 1):
            d = json.loads(line)
            stored = d.pop("hash", None)
            s = System.from_dict(d)
            if stored is not None and stored != s.hash:
                raise ValueError(f"{path}:{line_no}: hash mismatch (file modified or corrupted)")
            yield s
