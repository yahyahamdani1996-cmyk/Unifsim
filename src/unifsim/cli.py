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
    "periods": "2,3,4,5,6,10,12,15,20,30,60",
    "u_min": "1/100",
    "quantum": "1/10000",
    "speeds": "1-10",
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


def label_load(x: Fraction) -> str:
    return f"{float(x):g}"


# ------------------------------------------------------------------ gen
def _one(job):
    n, i, kw = job
    from .gen import regenerate
    return i, regenerate(n=n, index=i, **kw)


def cmd_gen(a) -> int:
    from .gen import write_bank
    from .model.platform import Platform

    if (a.platform is None) == (a.m is None):
        raise SystemExit("unifsim gen: give either --platform SPEEDS (fixed) or --m M (random speeds)")
    if (a.U is None) == (a.load is None):
        raise SystemExit("unifsim gen: give either --U or --load")
    if a.m is not None and a.U is not None:
        raise SystemExit("unifsim gen: with --m (random platform) give --load, U = load x S_m")

    kw = dict(master_seed=a.seed, periods=tuple(int(p) for p in a.periods.split(",")),
              u_min=a.u_min, u_max=a.u_max, quantum=a.quantum, rounding=a.rounding, order=a.order)
    if a.platform is not None:
        platform = Platform(speeds(a.platform))
        if platform.speeds[-1] != 1:
            print(f"warning: slowest speed is {platform.speeds[-1]}, convention is 1", file=sys.stderr)
        kw["platform"] = platform
        m = platform.m
    else:
        lo, hi = (int(x) for x in a.speeds.split("-"))
        kw.update(m=a.m, speed_range=(lo, hi))
        m = a.m

    ns = [int(n) for n in values(a.n)]
    targets = [("U", u) for u in values(a.U)] if a.U is not None else [("load", x) for x in values(a.load)]
    indices = [a.index] if a.index is not None else list(range(a.count))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    with ProcessPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        for n in ns:
            for kind, value in targets:
                t0 = time.time()
                name = f"m{m}_n{n}_" + (f"U{label(value)}" if kind == "U" else f"load{label_load(value)}")
                point_kw = dict(kw, **({"U": value} if kind == "U" else {"load": value}))
                if a.bank:
                    path = out / f"{name}.jsonl.gz"
                    results = sorted(pool.map(_one, [(n, i, point_kw) for i in indices], chunksize=8))
                    write_bank(path, (s for _, s in results))
                    done, where = len(results), path
                else:
                    folder = out / name
                    folder.mkdir(parents=True, exist_ok=True)
                    todo = [(n, i, point_kw) for i in indices if not (folder / f"ts_{i:04d}.json").exists()]
                    for i, s in pool.map(_one, todo, chunksize=8):
                        s.save(folder / f"ts_{i:04d}.json")
                    done, where = len(todo), folder
                skipped = len(indices) - done
                total += done
                msg = f"{name:<24} {done:>5} sets -> {where}"
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
    plat = g.add_argument_group("platform (one of)")
    plat.add_argument("--platform", default=None, help="fixed platform: speeds, e.g. 8,6,5,4,3,2,1,1")
    plat.add_argument("--m", type=int, default=None,
                      help="random platform: m processors, speeds drawn for each set (slowest = 1)")
    plat.add_argument("--speeds", default=DEFAULTS["speeds"], help="with --m: integer speed range lo-hi")
    util = g.add_argument_group("utilization (one of)")
    util.add_argument("--U", default=None, help="total utilization (fixed platform only): 18 | 6-30 | 37/2")
    util.add_argument("--load", default=None, help="U = load x S_m: 0.67 | 0.1-1/0.1")
    g.add_argument("--count", type=int, default=1, help="task sets per point")
    g.add_argument("--index", type=int, default=None, help="generate only set number INDEX of each point")
    g.add_argument("--out", default="Tasksets", help="output folder")
    g.add_argument("--bank", action="store_true", help="one .jsonl.gz file per point instead of one file per set")
    g.add_argument("--periods", default=DEFAULTS["periods"], help="periods to draw from")
    g.add_argument("--u-min", dest="u_min", default=DEFAULTS["u_min"], help="minimum task utilization")
    g.add_argument("--u-max", dest="u_max", default=None, help="maximum task utilization (default: fastest speed)")
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
