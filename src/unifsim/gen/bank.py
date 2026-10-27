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

from ..model.system import System
from .cfs_uniform import cfs_uniform
from .seeds import derive_seed

GENERATORS = {"cfs_uniform": cfs_uniform}


def set_seed(master_seed, n, U, index) -> int:
    return derive_seed("set", master_seed, n, U, index)


def regenerate(n, U, index, master_seed, generator="cfs_uniform", **params) -> System:
    system = GENERATORS[generator](n=n, U=U, seed=set_seed(master_seed, n, U, index), **params)
    system.meta.update({"master_seed": master_seed, "index": index})
    return system


def point(n, U, count, master_seed, generator="cfs_uniform", **params):
    """Yield the `count` task sets of the campaign point (n, U)."""
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
