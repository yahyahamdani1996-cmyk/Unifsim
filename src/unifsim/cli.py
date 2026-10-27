"""Command line: unifsim <command> [options].   unifsim gen --help

v1 commands: gen.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
from pathlib import Path

DEFAULTS = {
    "platform": "8,6,5,4,3,2,1,1",
    "periods": "2,3,4,5,6,10,12,15,20,30,60",
    "u_min": "1/100",
    "u_max": "8",
    "quantum": "1/10000",
    "seed": 2026,
}


# ------------------------------------------------------------------ parsing helpers
def values(text: str) -> list[Fraction]:
    """'20' | '8,12,20' | '6-30' (step 1) | '8-40/4' (step 4) | '6-30/2,40' -> exact values."""
    out = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part[1:]:
            rng, _, step = part.partition("/")
            lo, hi = rng.split("-", 1)
            lo, hi, step = Fraction(lo), Fraction(hi), Fraction(step or 1)
            if step <= 0 or hi < lo:
                raise argparse.ArgumentTypeError(f"bad range {part!r}")
            v = lo
            while v <= hi:
                out.append(v)
                v += step
        else:
            out.append(Fraction(part))
    return out


def speeds(text: str) -> tuple[Fraction, ...]:
    return tuple(sorted((Fraction(x) for x in text.split(",")), reverse=True))


def label(x: Fraction) -> str:
    return str(x).replace("/", "_")


# ------------------------------------------------------------------ gen
def _one(job):
    n, U, i, kw = job
    from .gen import regenerate
    s = regenerate(n=n, U=U, index=i, **kw)
    return i, s


def cmd_gen(a) -> int:
    from .gen import write_bank
    from .model.platform import Platform

    kw = dict(master_seed=a.seed, platform=Platform(speeds(a.platform)),
              periods=tuple(int(p) for p in a.periods.split(",")),
              u_min=a.u_min, u_max=a.u_max, quantum=a.quantum,
              rounding=a.rounding, order=a.order)
    ns = [int(n) for n in values(a.n)]
    Us = values(a.U)
    indices = [a.index] if a.index is not None else list(range(a.count))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    workers = max(1, a.jobs)
    total = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for n in ns:
            for U in Us:
                t0 = time.time()
                folder = out / f"n{n}_U{label(U)}"
                if a.bank:
                    path = out / f"n{n}_U{label(U)}.jsonl.gz"
                    todo = [(n, U, i, kw) for i in indices]
                    results = sorted(pool.map(_one, todo, chunksize=8))
                    write_bank(path, (s for _, s in results))
                    done, where = len(results), path
                else:
                    folder.mkdir(parents=True, exist_ok=True)
                    todo = [(n, U, i, kw) for i in indices if not (folder / f"ts_{i:04d}.json").exists()]
                    for i, s in pool.map(_one, todo, chunksize=8):
                        s.save(folder / f"ts_{i:04d}.json")
                    done, where = len(todo), folder
                skipped = len(indices) - done
                total += done
                msg = f"n={n:<3} U={str(U):<6} {done:>5} sets -> {where}"
                if skipped:
                    msg += f"  ({skipped} already there)"
                print(f"{msg}  [{time.time() - t0:.1f}s]", flush=True)
    print(f"done: {total} task sets")
    return 0


# ------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="unifsim", description="Real-time scheduling on uniform multiprocessors.")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("gen", help="generate task sets (cfs_uniform)",
                       formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                       description="Generate feasible task sets, tasks sorted by non-increasing utilization. "
                                   "Same command = same sets. Existing files are kept (resume).")
    g.add_argument("--n", required=True, help="number of tasks: 20 | 8,12,20 | 8-40/4")
    g.add_argument("--U", required=True, help="total utilization: 18 | 6-30 | 6-30/2 | 37/2")
    g.add_argument("--count", type=int, default=1, help="task sets per (n, U)")
    g.add_argument("--index", type=int, default=None, help="generate only set number INDEX of each (n, U)")
    g.add_argument("--out", default="Tasksets", help="output folder")
    g.add_argument("--bank", action="store_true", help="one .jsonl.gz file per (n, U) instead of one file per set")
    g.add_argument("--platform", default=DEFAULTS["platform"], help="speeds, comma separated")
    g.add_argument("--periods", default=DEFAULTS["periods"], help="periods to draw from")
    g.add_argument("--u-min", dest="u_min", default=DEFAULTS["u_min"], help="minimum task utilization")
    g.add_argument("--u-max", dest="u_max", default=DEFAULTS["u_max"], help="maximum task utilization")
    g.add_argument("--quantum", default=DEFAULTS["quantum"], help="utilization quantum")
    g.add_argument("--rounding", choices=["exact_sum", "independent"], default="exact_sum",
                   help="exact_sum: utilizations sum to U exactly; independent: shrimp rounding")
    g.add_argument("--order", choices=["sorted", "random"], default="sorted", help="task order")
    g.add_argument("--seed", type=int, default=DEFAULTS["seed"], help="change only to draw another family")
    g.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="parallel workers")
    g.set_defaults(func=cmd_gen)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.func(a)
    except KeyboardInterrupt:
        print("interrupted: rerun the same command to resume", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
