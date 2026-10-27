"""HTML report: simulate one system with several algorithms and compare them.

    from unifsim.gui import compare
    compare(system, ["pcg_star", "g_edf"], "report.html")

The page shows, for each algorithm, a Gantt chart (same time scale for all,
TL-plane boundaries dashed, hover a block for its details) and one table with
the metrics side by side (best value of each row in bold). Self-contained HTML,
no dependency, opens in any browser.
"""

from __future__ import annotations

import html
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from ..engine import SimulationError, simulate
from ..metrics import compute_metrics
from ..schedulers.registry import make
from ..validate import ValidationError, validate

PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
           "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]

ROWS = [  # (label, attribute or callable, lower is better?)
    ("Job preemptions (total)", "total_job_preemptions", True),
    ("  local", "local_job_preemptions", True),
    ("  boundary", "boundary_job_preemptions", True),
    ("Job migrations (total)", "total_job_migrations", True),
    ("  local", "local_job_migrations", True),
    ("  boundary", "boundary_job_migrations", True),
    ("Task migrations (total)", "total_task_migrations", True),
    ("  between successive jobs", "total_boundary_task_migrations", True),
    ("Preemptions per job", lambda m: m.per_job_value("total_job_preemptions"), True),
    ("Migrations per job", lambda m: m.per_job_value("total_job_migrations"), True),
    ("R/D avg (jobs)", "avg_response_time_ratio", True),
    ("R/D worst (jobs)", "worst_response_time_ratio", True),
    ("R/D best (jobs)", "best_response_time_ratio", True),
    ("R/D avg (per task)", "avg_response_time_ratio_per_task", True),
    ("R/D worst (per task)", "worst_response_time_ratio_per_task", True),
    ("R/D best (per task)", "best_response_time_ratio_per_task", True),
]


def run(system, algorithm: str, horizon=None) -> dict:
    """Simulate, validate and measure one algorithm. Never raises: failures are reported."""
    out = {"name": algorithm, "trace": None, "metrics": None, "error": None}
    try:
        trace = simulate(system, make(algorithm), horizon)
        validate(system, trace)
        out["trace"], out["metrics"] = trace, compute_metrics(system, trace)
    except (SimulationError, ValidationError) as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def compare(system, algorithms, path="report.html", horizon=None, title=None) -> Path:
    results = [run(system, a, horizon) for a in algorithms]
    return write_report(system, results, path, horizon, title)


def write_report(system, results, path, horizon=None, title=None) -> Path:
    """Write the HTML page for results already computed by run() (one or several algorithms)."""
    H = Fraction(system.hyperperiod if horizon is None else horizon)
    page = _page(system, results, H, title or "unifsim comparison")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(page, encoding="utf-8")
    return p


# ---------------------------------------------------------------- rendering
def _fmt(v):
    if v is None:
        return "–"
    if isinstance(v, Fraction):
        return f"{float(v):.4f}"
    return str(v)


def _value(m, attr):
    return attr(m) if callable(attr) else getattr(m, attr)


def _ticks(H):
    h = float(H)
    for step in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000):
        if h / step <= 16:
            break
    t, out = 0, []
    while t <= h + 1e-12:
        out.append(t)
        t += step
    return out


def _gantt(system, trace, H):
    m = system.platform.m
    left, width, row, top = 92, 860, 34, 26
    height = top + m * row + 30
    X = lambda t: left + float(t) / float(H) * width
    parts = [f'<svg viewBox="0 0 {left + width + 20} {height}" class="gantt" role="img">']
    for t in _ticks(H):
        x = X(t)
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{top - 6}" y2="{top + m * row}" class="grid"/>'
                     f'<text x="{x:.2f}" y="{top - 10}" class="tick">{t:g}</text>')
    bounds = sorted({p.t0 for p in trace.planes} | {p.t1 for p in trace.planes})
    for b in bounds[1:-1]:
        x = X(b)
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{top}" y2="{top + m * row}" class="plane"/>')
    for p in range(m):
        y = top + p * row
        parts.append(f'<rect x="{left}" y="{y + 3}" width="{width}" height="{row - 6}" class="lane"/>'
                     f'<text x="{left - 10}" y="{y + row / 2 + 4}" class="proc">P{p + 1}'
                     f'<tspan class="speed"> s={system.platform.speeds[p]}</tspan></text>')
    ids = sorted(t.id for t in system.tasks)
    for s in trace.segments:
        x0, x1 = X(s.start), X(s.end)
        y = top + s.proc * row
        color = PALETTE[ids.index(s.job.task_id) % len(PALETTE)]
        tip = html.escape(f"{s.job.name} on P{s.proc + 1}  [{s.start}, {s.end})  "
                          f"work {(s.end - s.start) * system.platform.speeds[s.proc]}")
        parts.append(f'<g><title>{tip}</title><rect x="{x0:.2f}" y="{y + 5}" width="{max(x1 - x0, 0.6):.2f}" '
                     f'height="{row - 10}" rx="3" fill="{color}"/>')
        if x1 - x0 > 7.5 * len(s.job.name) + 6:
            parts.append(f'<text x="{(x0 + x1) / 2:.2f}" y="{y + row / 2 + 4}" class="label">'
                         f'{html.escape(s.job.name)}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def _table(results):
    ok = [r for r in results if r["metrics"] is not None]
    head = "".join(f"<th>{html.escape(r['name'])}</th>" for r in results)
    body = []
    for label, attr, lower in ROWS:
        vals = {r["name"]: _value(r["metrics"], attr) for r in ok}
        present = [v for v in vals.values() if v is not None]
        best = (min(present) if lower else max(present)) if len(present) > 1 else None
        cells = []
        for r in results:
            if r["metrics"] is None:
                cells.append('<td class="fail">failed</td>')
                continue
            v = vals[r["name"]]
            cls = ' class="best"' if best is not None and v == best and present.count(best) < len(present) else ""
            cells.append(f"<td{cls}>{_fmt(v)}</td>")
        sub = ' class="sub"' if label.startswith("  ") else ""
        body.append(f"<tr{sub}><th>{html.escape(label.strip())}</th>{''.join(cells)}</tr>")
    return f'<table class="metrics"><thead><tr><th>Metric</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def _page(system, results, H, title):
    tasks = "".join(
        f'<tr><td><span class="dot" style="background:{PALETTE[i % len(PALETTE)]}"></span>τ{t.id}</td>'
        f"<td>{t.C}</td><td>{t.T}</td><td>{t.D}</td><td>{float(t.u):.3f}</td></tr>"
        for i, t in enumerate(sorted(system.tasks, key=lambda t: t.id)))
    sections = []
    for r in results:
        if r["error"]:
            body = f'<p class="error">{html.escape(r["error"])}</p>'
            status = '<span class="badge bad">failed</span>'
        else:
            body = _gantt(system, r["trace"], H)
            status = '<span class="badge good">valid</span>'
        sections.append(f'<section class="card"><h2>{html.escape(r["name"])} {status}</h2>{body}</section>')
    speeds = ", ".join(str(s) for s in system.platform.speeds)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --ink:#1d2330; --muted:#667085; --line:#e4e7ec; --lane:#f2f4f7;
        --good:#12805c; --bad:#c4320a; --accent:#2e5bba; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0f1218; --card:#171b23; --ink:#e7eaf0; --muted:#98a2b3; --line:#2a303c; --lane:#1e232d;
          --good:#3ccb8f; --bad:#ff7a59; --accent:#7aa2ff; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
       font:14px/1.45 -apple-system, "Segoe UI", Inter, Roboto, sans-serif; }}
main {{ max-width:1080px; margin:0 auto; padding:28px 16px 48px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:0 0 12px; }}
.sub-title {{ color:var(--muted); margin:0 0 20px; }}
.grid2 {{ display:grid; grid-template-columns: 1fr 2fr; gap:16px; }}
@media (max-width: 760px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; margin-bottom:16px; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric: tabular-nums; }}
th, td {{ padding:6px 10px; border-bottom:1px solid var(--line); text-align:right; }}
th:first-child, td:first-child {{ text-align:left; }}
thead th {{ color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
tbody th {{ font-weight:500; }}
tr.sub th {{ padding-left:26px; color:var(--muted); font-weight:400; }}
td.best {{ font-weight:700; color:var(--accent); }}
td.fail {{ color:var(--bad); }}
.dot {{ display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:8px; vertical-align:-1px; }}
.badge {{ font-size:11px; font-weight:600; padding:2px 8px; border-radius:99px; margin-left:6px; vertical-align:2px; }}
.badge.good {{ background:color-mix(in srgb, var(--good) 15%, transparent); color:var(--good); }}
.badge.bad {{ background:color-mix(in srgb, var(--bad) 15%, transparent); color:var(--bad); }}
.error {{ color:var(--bad); font-family: ui-monospace, monospace; font-size:13px; }}
.gantt {{ width:100%; height:auto; display:block; }}
.gantt .lane {{ fill:var(--lane); }} .gantt .grid {{ stroke:var(--line); }}
.gantt .plane {{ stroke:var(--muted); stroke-dasharray:4 4; }}
.gantt .tick {{ fill:var(--muted); font-size:11px; text-anchor:middle; }}
.gantt .proc {{ fill:var(--ink); font-size:12px; font-weight:600; text-anchor:end; }}
.gantt .speed {{ fill:var(--muted); font-weight:400; }}
.gantt .label {{ fill:#fff; font-size:10.5px; font-weight:600; text-anchor:middle; pointer-events:none; }}
.gantt g:hover rect {{ opacity:.8; }}
.note {{ color:var(--muted); font-size:12px; margin-top:8px; }}
</style></head><body><main>
<h1>{html.escape(title)}</h1>
<p class="sub-title">n = {system.n} tasks · m = {system.platform.m} processors (speeds {speeds}) ·
U = {system.U} ({float(system.U):.3f}) · horizon {H} · generated {datetime.now():%Y-%m-%d %H:%M}</p>
<div class="grid2">
<section class="card"><h2>System</h2><table><thead><tr><th>Task</th><th>C</th><th>T</th><th>D</th><th>u</th></tr></thead>
<tbody>{tasks}</tbody></table></section>
<section class="card"><h2>Metrics</h2>{_table(results)}
<p class="note">Bold: best value of the row (lower is better). Local / boundary only for TL-plane algorithms.</p></section>
</div>
{''.join(sections)}
<p class="note">Same time scale for every chart. Dashed lines: TL-plane boundaries. Hover a block for its details.</p>
</main></body></html>"""
