"""Command line: unifsim <command> [options].   unifsim <command> --help

  gen       generate task sets (files or banks)
  simulate  one system, one scheduler: validation + metrics (+ schedule)
  compare   one system, several schedulers: metrics side by side + HTML report
  list      available schedulers

A system is given either as a JSON file, or by the generator options
(--platform/--m, --n, --U/--load, --index): the same set as `unifsim gen` would write.
"""

from __future__ import annotations

import argparse
import json
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


def point_name(m, n, kind, value) -> str:
    return f"m{m}_n{n}_" + (f"U{label(value)}" if kind == "U" else f"load{label_load(value)}")


# ------------------------------------------------------------------ generator options
def add_gen_args(p, required: bool):
    p.add_argument("--n", required=required, default=None, help="number of tasks: 20 | 8,12,20 | 8-40/4")
    plat = p.add_argument_group("platform (one of)")
    plat.add_argument("--platform", default=None, help="fixed platform: speeds, e.g. 8,6,5,4,3,2,1,1")
    plat.add_argument("--m", type=int, default=None,
                      help="random platform: m processors, speeds drawn for each set (slowest = 1)")
    plat.add_argument("--speeds", default=DEFAULTS["speeds"], help="with --m: integer speed range lo-hi")
    util = p.add_argument_group("utilization (one of)")
    util.add_argument("--U", default=None, help="total utilization (fixed platform only): 18 | 6-30 | 37/2")
    util.add_argument("--load", default=None, help="U = load x S_m: 0.67 | 0.1-1/0.1")
    gen = p.add_argument_group("generator")
    gen.add_argument("--periods", default=DEFAULTS["periods"], help="periods to draw from")
    gen.add_argument("--u-min", dest="u_min", default=DEFAULTS["u_min"], help="minimum task utilization")
    gen.add_argument("--u-max", dest="u_max", default=None, help="maximum task utilization (default: fastest speed)")
    gen.add_argument("--quantum", default=DEFAULTS["quantum"], help="utilization quantum")
    gen.add_argument("--rounding", choices=["exact_sum", "independent"], default="exact_sum",
                     help="exact_sum: utilizations sum to U exactly; independent: shrimp rounding")
    gen.add_argument("--order", choices=["sorted", "random"], default="sorted", help="task order")
    gen.add_argument("--seed", type=int, default=DEFAULTS["seed"], help="change only to draw another family")


def gen_kwargs(a, cmd):
    """Validated generator keyword arguments (without n / U / load) and m."""
    from .model.platform import Platform

    if (a.platform is None) == (a.m is None):
        raise SystemExit(f"unifsim {cmd}: give either --platform SPEEDS (fixed) or --m M (random speeds)")
    if (a.U is None) == (a.load is None):
        raise SystemExit(f"unifsim {cmd}: give either --U or --load")
    if a.m is not None and a.U is not None:
        raise SystemExit(f"unifsim {cmd}: with --m (random platform) give --load, U = load x S_m")
    kw = dict(master_seed=a.seed, periods=tuple(int(p) for p in a.periods.split(",")),
              u_min=a.u_min, u_max=a.u_max, quantum=a.quantum, rounding=a.rounding, order=a.order)
    if a.platform is not None:
        platform = Platform(speeds(a.platform))
        if platform.speeds[-1] != 1:
            print(f"warning: slowest speed is {platform.speeds[-1]}, convention is 1", file=sys.stderr)
        kw["platform"] = platform
        return kw, platform.m
    lo, hi = (int(x) for x in a.speeds.split("-"))
    kw.update(m=a.m, speed_range=(lo, hi))
    return kw, a.m


def targets(a):
    return [("U", u) for u in values(a.U)] if a.U is not None else [("load", x) for x in values(a.load)]


# ------------------------------------------------------------------ gen
def _one(job):
    n, i, kw = job
    from .gen import regenerate
    return i, regenerate(n=n, index=i, **kw)


def cmd_gen(a) -> int:
    from .gen import write_bank

    kw, m = gen_kwargs(a, "gen")
    ns = [int(n) for n in values(a.n)]
    indices = [a.index] if a.index is not None else list(range(a.count))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    with ProcessPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        for n in ns:
            for kind, value in targets(a):
                t0 = time.time()
                name = point_name(m, n, kind, value)
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


# ------------------------------------------------------------------ one system (simulate / compare)
def load_system(a, cmd):
    """(system, name) from a JSON file or from the generator options."""
    from .model.system import System

    if a.file is not None:
        if a.n is not None or a.platform is not None or a.m is not None:
            raise SystemExit(f"unifsim {cmd}: give either a file or generator options, not both")
        path = Path(a.file)
        if path.is_dir():
            raise SystemExit(f"unifsim {cmd}: {path} is a folder; {cmd} takes one system "
                             f"(many systems = a campaign)")
        if not path.exists():
            raise SystemExit(f"unifsim {cmd}: {path} not found")
        return System.load(path), f"{path.parent.name}/{path.stem}"

    if a.n is None:
        raise SystemExit(f"unifsim {cmd}: give a system file, or --n with the platform and utilization options")
    from .gen import regenerate
    kw, m = gen_kwargs(a, cmd)
    ns, ts = values(a.n), targets(a)
    if len(ns) != 1 or len(ts) != 1:
        raise SystemExit(f"unifsim {cmd}: one value of --n and of --U/--load (ranges are for gen)")
    n, (kind, value) = int(ns[0]), ts[0]
    kw[kind] = value
    return regenerate(n=n, index=a.index, **kw), f"{point_name(m, n, kind, value)}/ts_{a.index:04d}"


def system_line(system, name) -> str:
    speeds_txt = ",".join(str(s) for s in system.platform.speeds)
    feas = "feasible" if system.horvath_feasible() else "NOT feasible (Horvath)"
    return (f"system  {name}   n={system.n} m={system.platform.m} speeds=({speeds_txt}) "
            f"U={system.U} ({float(system.U):.3f}) H={system.hyperperiod}  {feas}")


def html_path(a, stem) -> Path:
    """--out if given (kept), otherwise a temporary file (nothing stored in the project)."""
    if a.out:
        return Path(a.out)
    import tempfile
    fd, name = tempfile.mkstemp(prefix=f"unifsim_{stem}_", suffix=".html")
    os.close(fd)
    return Path(name)


def show(path: Path, kept: bool, open_it: bool) -> None:
    print(f"\n{'report' if kept else 'temporary report'}: {path.resolve()}")
    if open_it:
        import webbrowser
        webbrowser.open(path.resolve().as_uri())


def check_tikz(a):
    if getattr(a, "tikz", None):
        raise SystemExit("unifsim: --tikz (LaTeX export) is reserved and not implemented yet")


def _check_arrivals(a):
    if a.arrivals != "periodic":
        raise SystemExit("unifsim: only --arrivals periodic is implemented")


def cmd_simulate(a) -> int:
    from .engine import SimulationError
    from .validate import ValidationError
    from .api import run

    _check_arrivals(a)
    check_tikz(a)
    system, name = load_system(a, "simulate")
    print(system_line(system, name))
    try:
        r = run(system, a.scheduler, horizon=a.horizon)
    except (SimulationError, ValidationError) as e:
        print(f"{a.scheduler}  FAILED  {type(e).__name__}: {e}")
        if a.json:
            Path(a.json).write_text(json.dumps({"system": name, "hash": system.hash, "scheduler": a.scheduler,
                                                "status": "failed", "error": str(e)}, indent=2))
        if a.gantt or a.out:                       # the report shows the failure too
            from .gui.report import write_report
            path = write_report(system, [{"name": a.scheduler, "trace": None, "metrics": None,
                                          "error": f"{type(e).__name__}: {e}"}],
                                html_path(a, "gantt"), a.horizon, title=name)
            show(path, bool(a.out), not a.no_open)
        return 1
    print(f"{a.scheduler}  VALID")
    print(r.metrics.report())
    if a.schedule:
        print()
        r.schedule()
    if a.json:
        Path(a.json).write_text(json.dumps({"system": name, "hash": system.hash, "scheduler": a.scheduler,
                                            "status": "ok", "metrics": r.metrics.as_row()}, indent=2))
        print(f"metrics written to {a.json}")
    if a.gantt or a.out:
        from .gui.report import write_report
        path = write_report(system, [{"name": a.scheduler, "trace": r.trace, "metrics": r.metrics, "error": None}],
                            html_path(a, "gantt"), a.horizon, title=name)
        show(path, bool(a.out), not a.no_open)
    return 0


def cmd_compare(a) -> int:
    from .gui.report import ROWS, _fmt, _value, write_report

    _check_arrivals(a)
    check_tikz(a)
    system, name = load_system(a, "compare")
    print(system_line(system, name))
    algos = [x.strip() for x in a.schedulers.split(",") if x.strip()]
    from .gui.report import run as run_one
    results = [run_one(system, x, a.horizon) for x in algos]

    width = max(len(x) for x in algos) + 2
    print(f"\n{'':32}" + "".join(f"{x:>{max(width, 12)}}" for x in algos))
    for lab, attr, _ in ROWS:
        cells = []
        for r in results:
            cells.append("failed" if r["metrics"] is None else _fmt(_value(r["metrics"], attr)))
        print(f"{lab:32}" + "".join(f"{c:>{max(width, 12)}}" for c in cells))
    for r in results:
        if r["error"]:
            print(f"{r['name']}: {r['error']}")

    path = write_report(system, results, html_path(a, "compare"), a.horizon, title=name)
    show(path, bool(a.out), not a.no_open)
    return 0


def cmd_list(a) -> int:
    from .schedulers.registry import REGISTRY

    for name in sorted(REGISTRY):
        try:
            s = REGISTRY[name]()
            kind = type(s).__name__
            budget = getattr(s, "budget", None)
            extra = f"  allocation={getattr(budget, '__name__', budget)}" if budget is not None else ""
            print(f"{name:20} {kind}{extra}")
        except Exception as e:                      # a scheduler being written
            print(f"{name:20} (cannot be built: {type(e).__name__}: {e})")
    return 0


# ------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="unifsim", description="Real-time scheduling on uniform multiprocessors.")
    sub = p.add_subparsers(dest="command", required=True)
    fmt = argparse.ArgumentDefaultsHelpFormatter

    g = sub.add_parser("gen", help="generate task sets", formatter_class=fmt,
                       description="Generate feasible task sets, tasks sorted by non-increasing utilization. "
                                   "Same command = same sets. Existing files are kept (resume).")
    add_gen_args(g, required=True)
    g.add_argument("--count", type=int, default=1, help="task sets per point")
    g.add_argument("--index", type=int, default=None, help="generate only set number INDEX of each point")
    g.add_argument("--out", default="Tasksets", help="output folder")
    g.add_argument("--bank", action="store_true", help="one .jsonl.gz file per point instead of one file per set")
    g.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="parallel workers")
    g.set_defaults(func=cmd_gen)

    def one_system(sp):
        sp.add_argument("file", nargs="?", default=None, help="system JSON file (or use the generator options)")
        add_gen_args(sp, required=False)
        sp.add_argument("--index", type=int, default=0, help="with generator options: set number")
        sp.add_argument("--horizon", type=Fraction, default=None, help="simulation length (default: hyperperiod)")
        sp.add_argument("--arrivals", default="periodic", choices=["periodic"], help="arrival model")
        sp.add_argument("--out", default=None, help="keep the HTML report in this file (default: temporary file)")
        sp.add_argument("--no-open", action="store_true", help="do not open the report in the browser")
        sp.add_argument("--tikz", default=None, metavar="FILE.tex",
                        help="LaTeX/TikZ export of the schedule (reserved, not implemented yet)")

    s = sub.add_parser("simulate", help="simulate one system with one scheduler", formatter_class=fmt,
                       description="Simulate, validate and measure one system. Examples:\n"
                                   "  unifsim simulate Tasksets/m8_n20_U18/ts_0000.json --scheduler pcg_star\n"
                                   "  unifsim simulate --platform 8,6,5,4,3,2,1,1 --n 20 --U 18 --scheduler pcg_star")
    one_system(s)
    s.add_argument("--scheduler", required=True, help="scheduler name (unifsim list)")
    s.add_argument("--schedule", action="store_true", help="also print the schedule")
    s.add_argument("--json", default=None, help="write the metrics to this JSON file")
    s.add_argument("--gantt", action="store_true", help="open the Gantt chart and metrics in the browser")
    s.set_defaults(func=cmd_simulate)

    c = sub.add_parser("compare", help="compare schedulers on one system (HTML report)", formatter_class=fmt)
    one_system(c)
    c.add_argument("--schedulers", required=True, help="comma separated, e.g. pcg_star,wc_pcg_star,g_edf")
    c.set_defaults(func=cmd_compare)

    li = sub.add_parser("list", help="list the available schedulers")
    li.set_defaults(func=cmd_list)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.func(a)
    except KeyboardInterrupt:
        print("interrupted: rerun the same command to resume", file=sys.stderr)
        return 130
    except BrokenPipeError:                       # output piped to head, less, ...
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
