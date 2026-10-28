"""Run a campaign: every scheduler on every set of every grid point, one CSV row
per (set, scheduler), never stopping on a failed run, resumable.

Results folder results/<name>/:
    rows.csv     one row per (set, scheduler)
    spec.toml    the spec (latest run)
    meta.json    unifsim version, git commit, machine, run sessions
    failures/    the systems of the failed runs (replay with unifsim simulate)
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform as _platform
import shutil
import subprocess
import sys
import time
from dataclasses import fields
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from .spec import SpecError, parse

KEY = ["point", "n", "m", "U", "load", "index", "system_hash", "scheduler"]
OUTCOME = ["success", "status", "feasible", "miss_time", "miss_job", "error", "runtime_s", "schedule_hash"]
# statuses; success = 1 only for "ok". "generation_error": no set, success left empty
STATUSES = ("ok", "deadline_miss", "budget_infeasible", "invalid_decision", "invalid_trace", "error",
            "generation_error")
# spec keys that may change between two runs of the same campaign (extend it); the others may not
EXTENSIBLE = {"count", "schedulers", "description"}


def metric_columns():
    from ..metrics import COUNTERS, Metrics
    cols = []
    for f in fields(Metrics):
        if f.name in ("scheduler", "n", "m", "per_job", "per_plane_preemptions"):
            continue
        cols.append(f.name)
        if "response_time_ratio" in f.name:
            cols.append(f.name + "_float")
    for c in COUNTERS:
        cols += [f"{c}_per_job", f"{c}_per_job_float"]
    return cols


def columns():
    return KEY + OUTCOME + metric_columns()


def _exact(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return int(v)
    return str(v)


def _metric_values(metrics):
    from ..metrics import COUNTERS
    row = {}
    for f in fields(metrics):
        if f.name in ("scheduler", "n", "m", "per_job", "per_plane_preemptions"):
            continue
        v = getattr(metrics, f.name)
        row[f.name] = _exact(v)
        if "response_time_ratio" in f.name:
            row[f.name + "_float"] = "" if v is None else f"{float(v):.6g}"
    for c in COUNTERS:
        v = metrics.per_job_value(c)
        row[f"{c}_per_job"] = _exact(v)
        row[f"{c}_per_job_float"] = "" if v is None else f"{float(v):.6g}"
    return row


def schedule_hash(trace) -> str:
    segs = sorted((s.proc, s.job.task_id, s.job.k, str(s.start), str(s.end)) for s in trace.segments)
    return hashlib.sha256(repr(segs).encode()).hexdigest()[:16]


def _classify(e):
    from ..engine import BudgetInfeasible, DeadlineMiss, InvalidDecision
    from ..validate import ValidationError
    if isinstance(e, DeadlineMiss):
        return "deadline_miss"
    if isinstance(e, BudgetInfeasible):
        return "budget_infeasible"
    if isinstance(e, InvalidDecision):
        return "invalid_decision"
    if isinstance(e, ValidationError):
        return "invalid_trace"
    return "error"


def run_one(system, scheduler):
    """One run -> (outcome dict, metrics row). Never raises."""
    from ..api import run
    t0 = time.perf_counter()
    try:
        r = run(system, scheduler)
    except Exception as e:                      # noqa: BLE001 - every failure becomes a row
        status = _classify(e)
        out = {"success": 0, "status": status, "error": f"{type(e).__name__}: {e}"[:500],
               "runtime_s": f"{time.perf_counter() - t0:.4f}"}
        if status == "deadline_miss":
            out["miss_time"], out["miss_job"] = str(e.t), e.job.name
        return out, {}
    out = {"success": 1, "status": "ok", "runtime_s": f"{time.perf_counter() - t0:.4f}",
           "schedule_hash": schedule_hash(r.trace)}
    return out, _metric_values(r.metrics)


def _key_values(point, system, index, load_value):
    S = sum(system.platform.speeds, Fraction(0))
    load = load_value if load_value is not None else system.U / S
    return {"point": point, "n": system.n, "m": system.platform.m, "U": str(system.U), "load": str(load),
            "index": index, "system_hash": system.hash}


def work(job):
    """Worker: (point name, index, system or generator kwargs, load, schedulers)
    -> (point, index, rows, failures). Runs in a separate process."""
    point, index, source, load_value, schedulers = job
    from ..model.system import System
    if isinstance(source, dict) and "gen" in source:
        from ..gen import regenerate
        try:
            system = regenerate(index=index, **source["gen"])
        except Exception as e:                  # noqa: BLE001
            rows = [{"point": point, "index": index, "scheduler": s, "status": "generation_error",
                     "error": f"{type(e).__name__}: {e}"[:500]} for s in schedulers]
            return point, index, rows, []
    else:
        system = System.from_dict(source)
    key = _key_values(point, system, index, load_value)
    feasible = int(system.horvath_feasible())
    rows, failures = [], []
    for s in schedulers:
        out, metrics = run_one(system, s)
        rows.append({**key, "scheduler": s, "feasible": feasible, **out, **metrics})
        if out["success"] == 0:
            failures.append((s, out))
    fail_systems = []
    for s, out in failures:
        d = json.loads(system.to_json())
        d["meta"] = dict(d.get("meta", {}), failure={"scheduler": s, "status": out["status"], "error": out.get("error", ""),
                                             "point": point, "index": index})
        fail_systems.append((f"{point}_ts{index:04d}_{s}.json", d))
    return point, index, rows, fail_systems


# ------------------------------------------------------------------ sources of sets
def _sets_from_files(path: Path, count):
    """[(point, [(index, system dict)])] from a `unifsim gen` folder or bank(s)."""
    from ..gen import read_bank
    from ..model.system import System

    def folder_sets(folder):
        files = sorted(folder.glob("ts_*.json"))[:count]
        return [(int(f.stem.split("_")[1]), json.loads(System.load(f).to_json())) for f in files]

    def bank_sets(bank):
        out = []
        for i, s in enumerate(read_bank(bank)):
            if i >= count:
                break
            out.append((i, json.loads(s.to_json())))
        return out

    if not path.exists():
        raise SpecError(f"tasksets: {path} not found")
    if path.is_file():
        return [(path.name.split(".")[0], bank_sets(path))]
    if any(path.glob("ts_*.json")):
        return [(path.name, folder_sets(path))]
    out = []
    for sub in sorted(path.iterdir()):
        if sub.is_dir() and any(sub.glob("ts_*.json")):
            out.append((sub.name, folder_sets(sub)))
        elif sub.name.endswith((".jsonl", ".jsonl.gz")):
            out.append((sub.name.split(".")[0], bank_sets(sub)))
    if not out:
        raise SpecError(f"tasksets: no ts_*.json or .jsonl(.gz) bank found in {path}")
    return out


def jobs_of(spec):
    """All (point, index, source, load, schedulers) of the campaign, before resume filtering."""
    out = []
    if spec.tasksets is not None:
        for point, sets in _sets_from_files(spec.tasksets, spec.count):
            for index, d in sets:
                out.append((point, index, d, None))
        return out
    for p in spec.points:
        load_value = str(p.value) if p.kind == "load" else None
        for i in range(spec.count):
            out.append((p.name, i, {"gen": p.gen}, None if load_value is None else Fraction(load_value)))
    return out


# ------------------------------------------------------------------ results folder
def _git_commit():
    here = Path(__file__).resolve().parent
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=here, capture_output=True, text=True,
                                timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=here, capture_output=True, text=True,
                               timeout=5).stdout.strip()
        return (commit + ("+dirty" if dirty else "")) or None
    except Exception:                           # noqa: BLE001 - not a git checkout
        return None


def _check_spec_change(folder: Path, spec):
    old_path = folder / "spec.toml"
    if not old_path.exists():
        return
    old = parse(old_path.read_text(encoding="utf-8"), str(old_path))
    a = {k: v for k, v in old.raw.items() if k not in EXTENSIBLE}
    b = {k: v for k, v in spec.raw.items() if k not in EXTENSIBLE}
    if a != b:
        changed = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        raise SpecError(f"{folder}: the spec changed since the first run ({', '.join(changed)}); "
                        f"only {sorted(EXTENSIBLE)} may change. Use another name, or --restart to delete the results.")


def _done_keys(rows_path: Path, cols):
    if not rows_path.exists():
        return set()
    with open(rows_path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if r.fieldnames != cols:
            raise SpecError(f"{rows_path}: columns differ from this unifsim version; use --restart or another name")
        return {(row["point"], int(row["index"]), row["scheduler"]) for row in r}


def _fmt_time(s):
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def run_campaign(spec_path, out="results", jobs=None, restart=False, quiet=False):
    """Run (or resume) the campaign of `spec_path`. Returns the results folder."""
    from ..schedulers.registry import make
    spec_path = Path(spec_path)
    text = spec_path.read_text(encoding="utf-8")
    spec = parse(text, str(spec_path))
    for s in spec.schedulers:                   # fail now, not in a worker
        try:
            make(s)
        except Exception as e:                  # noqa: BLE001
            raise SpecError(f"scheduler {s!r} cannot be built: {type(e).__name__}: {e}") from None

    folder = Path(out) / spec.name
    if restart and folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    _check_spec_change(folder, spec)
    cols = columns()
    rows_path = folder / "rows.csv"
    done = _done_keys(rows_path, cols)

    todo = []
    for point, index, source, load_value in jobs_of(spec):
        missing = [s for s in spec.schedulers if (point, index, s) not in done]
        if missing:
            todo.append((point, index, source, load_value, missing))
    total_sets = len(jobs_of(spec))

    (folder / "spec.toml").write_text(text, encoding="utf-8")
    meta_path = folder / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {
        "name": spec.name, "created": datetime.now().isoformat(timespec="seconds"), "sessions": []}
    from .. import __version__
    session = {"started": datetime.now().isoformat(timespec="seconds"), "unifsim": __version__,
               "git_commit": _git_commit(), "python": sys.version.split()[0],
               "machine": f"{_platform.node()} ({_platform.platform()}, {os.cpu_count()} cpus)",
               "sets_to_run": len(todo)}
    meta["sessions"].append(session)
    meta_path.write_text(json.dumps(meta, indent=2))

    say = (lambda *a, **k: None) if quiet else (lambda *a, **k: print(*a, **k, flush=True))
    say(f"campaign {spec.name}: {len(spec.points) or 'file'} point(s) x {spec.count} sets x "
        f"{len(spec.schedulers)} scheduler(s) -> {folder}")
    if len(todo) < total_sets:
        say(f"resume: {total_sets - len(todo)} of {total_sets} sets already done")
    if not todo:
        say("nothing to do")
        _finish(meta_path, meta, session, 0)
        return folder

    new_file = not rows_path.exists()
    fails_dir = folder / "failures"
    stats = {"sets": 0, "runs": 0, "failed": 0}
    t0 = last = time.time()
    tty = sys.stdout.isatty()

    def record(result, writer, fh):
        point, index, rows, fail_systems = result
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in cols})
            stats["runs"] += 1
            stats["failed"] += row.get("success") == 0
        fh.flush()
        for name, d in fail_systems:
            fails_dir.mkdir(exist_ok=True)
            (fails_dir / name).write_text(json.dumps(d, indent=1))
        stats["sets"] += 1

    def progress(final=False):
        nonlocal last
        now = time.time()
        if not final and now - last < (1 if tty else 10):
            return
        last = now
        k, el = stats["sets"], now - t0
        rate = k / el if el > 0 else 0
        eta = (len(todo) - k) / rate if rate > 0 else 0
        line = (f"[{k}/{len(todo)} sets] {100 * k / len(todo):5.1f}%  {rate:.1f} sets/s  "
                f"elapsed {_fmt_time(el)}  left {_fmt_time(eta)}  failed runs {stats['failed']}")
        say(("\r" + line) if tty and not final else line, end="" if tty and not final else "\n")

    workers = jobs or os.cpu_count() or 1
    with open(rows_path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        if new_file:
            writer.writeheader()
        if workers == 1:
            for job in todo:
                record(work((*job[:3], job[3], job[4])), writer, fh)
                progress()
        else:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            pool = ProcessPoolExecutor(max_workers=workers)
            try:
                futures = [pool.submit(work, job) for job in todo]
                for fut in as_completed(futures):
                    record(fut.result(), writer, fh)
                    progress()
            except BaseException:
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            pool.shutdown()
    if tty:
        say("")
    progress(final=True)
    _finish(meta_path, meta, session, stats["runs"])
    say(f"done: {stats['runs']} runs, {stats['failed']} failed -> {rows_path}")
    if stats["failed"]:
        say(f"failed systems: {fails_dir}  (replay: unifsim simulate <file> --scheduler <name> --gantt)")
    say(f"report: unifsim campaign report {folder}")
    return folder


def _finish(meta_path, meta, session, runs):
    session["finished"] = datetime.now().isoformat(timespec="seconds")
    session["runs_written"] = runs
    meta_path.write_text(json.dumps(meta, indent=2))
