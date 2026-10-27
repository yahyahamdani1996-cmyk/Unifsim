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
import json
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


def _chart_data(system, trace):
    """Segments and TL-plane boundaries for the zoomable chart (floats to draw, exact strings to show)."""
    ids = sorted(t.id for t in system.tasks)
    sp = system.platform.speeds
    segs = [[s.proc, PALETTE[ids.index(s.job.task_id) % len(PALETTE)], s.job.name,
             float(s.start), float(s.end), str(s.start), str(s.end), str((s.end - s.start) * sp[s.proc])]
            for s in trace.segments]
    bounds = sorted({p.t0 for p in trace.planes} | {p.t1 for p in trace.planes})
    return {"segs": segs, "planes": [float(b) for b in bounds[1:-1]]}


def _gantt(system, trace, H, idx=0):
    m = system.platform.m
    left, width, row, top = 92, 860, 34, 26
    height = top + m * row + 30
    X = lambda t: left + float(t) / float(H) * width
    parts = [f'<svg viewBox="0 0 {left + width + 20} {height}" class="gantt" role="img" data-chart="{idx}">']
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
    sections, charts = [], {}
    for r in results:
        if r["error"]:
            body = f'<p class="error">{html.escape(r["error"])}</p>'
            status = '<span class="badge bad">failed</span>'
        else:
            idx = len(charts)
            charts[idx] = _chart_data(system, r["trace"])
            body = _gantt(system, r["trace"], H, idx)
            status = '<span class="badge good">valid</span>'
        sections.append(f'<section class="card"><h2>{html.escape(r["name"])} {status}</h2>{body}</section>')
    data = json.dumps({"H": float(H), "procs": [f"P{p + 1}" for p in range(system.platform.m)],
                       "speeds": [str(x) for x in system.platform.speeds], "charts": charts})
    toolbar = ('<div class="toolbar card"><b>Time window</b>'
               '<button id="zin" title="zoom in">+</button><button id="zout" title="zoom out">&minus;</button>'
               '<button id="zreset" title="whole horizon">&#10226;</button>'
               '<label>from <input id="vfrom" size="9"></label><label>to <input id="vto" size="9"></label>'
               '<button id="vapply">apply</button>'
               '<span class="hint">wheel: zoom &middot; drag: move &middot; double-click: reset</span></div>'
               if charts else "")
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
.toolbar {{ position:sticky; top:8px; z-index:5; display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:10px 14px; }}
.toolbar button {{ font:inherit; min-width:30px; padding:3px 10px; border:1px solid var(--line); border-radius:8px;
                  background:var(--bg); color:var(--ink); cursor:pointer; }}
.toolbar button:hover {{ border-color:var(--accent); }}
.toolbar input {{ font:inherit; padding:3px 6px; border:1px solid var(--line); border-radius:6px;
                 background:var(--bg); color:var(--ink); font-variant-numeric:tabular-nums; }}
.toolbar .hint {{ color:var(--muted); font-size:12px; margin-left:auto; }}
.gantt[data-chart] {{ cursor:grab; user-select:none; touch-action:none; }}
.gantt.dragging {{ cursor:grabbing; }}
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
{toolbar}
{''.join(sections)}
<p class="note">Same time window for every chart. Dashed lines: TL-plane boundaries. Hover a block for its details.</p>
</main>
<script>
const D = {data};
(() => {{
  const L = 92, W = 860, ROW = 34, TOP = 26, m = D.procs.length, HEIGHT = TOP + m * ROW + 30, VBW = L + W + 20;
  let v0 = 0, v1 = D.H;
  const svgs = [...document.querySelectorAll("svg.gantt[data-chart]")];
  if (!svgs.length) return;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}})[c]);
  const X = t => L + (t - v0) / (v1 - v0) * W;
  const step = span => {{ const raw = span / 12, p = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const f of [1, 2, 5, 10]) if (f * p >= raw) return f * p; return 10 * p; }};
  const fmt = (t, st) => {{ const d = Math.max(0, -Math.floor(Math.log10(st))); return t.toFixed(Math.min(d, 6)); }};
  function draw(svg) {{
    const c = D.charts[svg.dataset.chart], id = "clip" + svg.dataset.chart, st = step(v1 - v0);
    let h = `<defs><clipPath id="${{id}}"><rect x="${{L}}" y="0" width="${{W}}" height="${{HEIGHT}}"/></clipPath></defs>`;
    for (let t = Math.ceil(v0 / st) * st; t <= v1 + st * 1e-9; t += st) {{
      const x = X(t);
      h += `<line x1="${{x}}" x2="${{x}}" y1="${{TOP - 6}}" y2="${{TOP + m * ROW}}" class="grid"/>` +
           `<text x="${{x}}" y="${{TOP - 10}}" class="tick">${{fmt(t, st)}}</text>`;
    }}
    for (let p = 0; p < m; p++) {{
      const y = TOP + p * ROW;
      h += `<rect x="${{L}}" y="${{y + 3}}" width="${{W}}" height="${{ROW - 6}}" class="lane"/>` +
           `<text x="${{L - 10}}" y="${{y + ROW / 2 + 4}}" class="proc">${{D.procs[p]}}<tspan class="speed"> s=${{D.speeds[p]}}</tspan></text>`;
    }}
    h += `<g clip-path="url(#${{id}})">`;
    for (const b of c.planes) if (b > v0 && b < v1) {{ const x = X(b);
      h += `<line x1="${{x}}" x2="${{x}}" y1="${{TOP}}" y2="${{TOP + m * ROW}}" class="plane"/>`; }}
    for (const [p, col, name, s, e, se, ee, w] of c.segs) {{
      if (e <= v0 || s >= v1) continue;
      const x0 = X(Math.max(s, v0)), x1 = X(Math.min(e, v1)), y = TOP + p * ROW;
      h += `<g><title>${{esc(name)}} on P${{p + 1}}  [${{se}}, ${{ee}})  work ${{w}}</title>` +
           `<rect x="${{x0}}" y="${{y + 5}}" width="${{Math.max(x1 - x0, 0.6)}}" height="${{ROW - 10}}" rx="3" fill="${{col}}"/>`;
      if (x1 - x0 > 7.5 * name.length + 6) h += `<text x="${{(x0 + x1) / 2}}" y="${{y + ROW / 2 + 4}}" class="label">${{esc(name)}}</text>`;
      h += "</g>";
    }}
    svg.innerHTML = h + "</g>";
  }}
  const vf = document.getElementById("vfrom"), vt = document.getElementById("vto");
  function render() {{ svgs.forEach(draw); const st = step(v1 - v0) / 10; vf.value = fmt(v0, st); vt.value = fmt(v1, st); }}
  function setView(a, b) {{
    let span = Math.min(Math.max(b - a, D.H / 1e6), D.H);
    a = Math.min(Math.max(a, 0), D.H - span); v0 = a; v1 = a + span; render();
  }}
  const timeAt = (svg, clientX) => {{ const r = svg.getBoundingClientRect();
    return v0 + (((clientX - r.left) / r.width * VBW) - L) / W * (v1 - v0); }};
  const zoom = (f, c) => setView(c - (c - v0) * f, c - (c - v0) * f + (v1 - v0) * f);
  for (const svg of svgs) {{
    svg.addEventListener("wheel", e => {{ e.preventDefault();
      zoom(e.deltaY < 0 ? 1 / 1.25 : 1.25, Math.min(Math.max(timeAt(svg, e.clientX), v0), v1)); }}, {{passive: false}});
    svg.addEventListener("dblclick", () => setView(0, D.H));
    svg.addEventListener("pointerdown", e => {{
      const r = svg.getBoundingClientRect(), x0 = e.clientX, a = v0, b = v1;
      svg.setPointerCapture(e.pointerId); svg.classList.add("dragging");
      const move = ev => {{ const dt = (ev.clientX - x0) / r.width * VBW / W * (b - a); setView(a - dt, b - dt); }};
      const up = () => {{ svg.classList.remove("dragging"); svg.removeEventListener("pointermove", move);
        svg.removeEventListener("pointerup", up); }};
      svg.addEventListener("pointermove", move); svg.addEventListener("pointerup", up);
    }});
  }}
  const num = s => {{ s = s.trim(); if (s.includes("/")) {{ const [a, b] = s.split("/"); return +a / +b; }} return +s; }};
  document.getElementById("zin").onclick = () => zoom(1 / 1.5, (v0 + v1) / 2);
  document.getElementById("zout").onclick = () => zoom(1.5, (v0 + v1) / 2);
  document.getElementById("zreset").onclick = () => setView(0, D.H);
  document.getElementById("vapply").onclick = () => {{ const a = num(vf.value), b = num(vt.value);
    if (isFinite(a) && isFinite(b) && b > a) setView(a, b); }};
  for (const inp of [vf, vt]) inp.addEventListener("keydown", e => {{ if (e.key === "Enter") document.getElementById("vapply").click(); }});
  render();
}})();
</script>
</body></html>"""
