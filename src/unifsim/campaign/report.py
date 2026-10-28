"""Campaign report: reads results/<name>/rows.csv only and writes report.html.

For each grid point and scheduler: success ratio (all sets and feasible sets),
means with 95% confidence intervals over successful runs, failures by status,
paired comparison with the first scheduler on the same sets, and curves
(metric vs U or load, one curve per scheduler) when the grid varies U/load.
"""

from __future__ import annotations

import csv
import html
import json
import math
from collections import defaultdict
from datetime import datetime
from fractions import Fraction
from pathlib import Path

# categorical slots (validated reference palette), light / dark
SERIES = [("#2a78d6", "#3987e5"), ("#eb6834", "#d95926"), ("#1baf7a", "#199e70"), ("#eda100", "#c98500"),
          ("#e87ba4", "#d55181"), ("#008300", "#008300"), ("#6250d6", "#9085e9")]

METRICS = [  # (label, column, lower is better)
    ("Preemptions per job", "total_job_preemptions_per_job_float", True),
    ("Migrations per job", "total_job_migrations_per_job_float", True),
    ("Task migrations per job", "total_task_migrations_per_job_float", True),
    ("R/D avg (jobs)", "avg_response_time_ratio_float", True),
    ("Run time (s)", "runtime_s", True),
]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _mean_ci(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, None, 0
    k = len(xs)
    mu = sum(xs) / k
    if k < 2:
        return mu, 0.0, k
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (k - 1))
    return mu, 1.96 * sd / math.sqrt(k), k


X_CHOICES = ("auto", "n", "m", "U", "load")


def _point_axes(folder: Path, rows, x="auto"):
    """point -> (group label, x label, x value, sort key).

    x: the grid dimension drawn on the x axis ("n", "m", "U" or "load"); the other
    dimensions define the groups (one card of curves per group). "auto": the
    utilization if it varies, otherwise n, otherwise m."""
    from .spec import parse
    try:
        spec = parse((folder / "spec.toml").read_text(encoding="utf-8"))
        info = {p.name: (p.n, p.m, p.kind, p.value) for p in spec.points}
    except Exception:                        # noqa: BLE001 - tasksets campaigns or old spec
        info = {}
    loads = defaultdict(list)
    for r in rows:
        if r["load"]:
            loads[r["point"]].append(float(Fraction(r["load"])))
    names = {r["point"] for r in rows}
    if not info or not names <= set(info):
        out = {}
        for p in names:
            ls = loads.get(p) or [0.0]
            out[p] = ("sets from files", "mean load", sum(ls) / len(ls), (0, 0))
        return out

    kind = info[next(iter(names))][2]                    # "U" or "load", the same for every point
    varies = {d: len({_dim(info[p], d) for p in names}) > 1 for d in ("n", "m", kind)}
    if x == "auto":
        x = next((d for d in (kind, "n", "m") if varies[d]), kind)
    if x in ("U", "load") and x != kind:
        raise ValueError(f"--x {x}: this campaign varies {kind}, not {x}")
    if x not in ("n", "m", "U", "load"):
        raise ValueError(f"--x must be one of {X_CHOICES}")
    others = [d for d in ("n", "m", kind) if d != x]
    out = {}
    for p in names:
        group = ", ".join(f"{d} = {_label(_dim(info[p], d))}" for d in others)
        out[p] = (group, x, float(_dim(info[p], x)), tuple(_dim(info[p], d) for d in others))
    return out


def _dim(info, d):
    n, m, kind, value = info
    return {"n": n, "m": m}.get(d, value)


def _label(v):
    return f"{float(v):g}" if isinstance(v, Fraction) else str(v)


def summarize(folder, x="auto"):
    folder = Path(folder)
    with open(folder / "rows.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{folder}/rows.csv has no rows")
    schedulers = list(dict.fromkeys(r["scheduler"] for r in rows))
    try:
        from .spec import parse
        order = parse((folder / "spec.toml").read_text(encoding="utf-8")).schedulers
        schedulers = [s for s in order if s in schedulers] + [s for s in schedulers if s not in order]
    except Exception:                        # noqa: BLE001
        pass
    axes = _point_axes(folder, rows, x)
    points = sorted(axes, key=lambda p: (axes[p][3], axes[p][0], axes[p][2], p))

    groups = defaultdict(list)
    for r in rows:
        groups[r["point"], r["scheduler"]].append(r)
    cell = {}
    for p in points:
        for s in schedulers:
            rs = groups.get((p, s), [])
            gen_err = sum(r["status"] == "generation_error" for r in rs)
            rs = [r for r in rs if r["status"] != "generation_error"]
            ok = [r for r in rs if r["success"] == "1"]
            feas = [r for r in rs if r["feasible"] == "1"]
            status = defaultdict(int)
            for r in rs:
                status[r["status"]] += 1
            cell[p, s] = {
                "sets": len(rs), "gen_err": gen_err, "ok": len(ok),
                "success": len(ok) / len(rs) if rs else None,
                "feasible": len(feas),
                "success_feasible": (sum(r["success"] == "1" for r in feas) / len(feas)) if feas else None,
                "status": dict(status),
                "metrics": {col: _mean_ci([_f(r[col]) for r in ok]) for _, col, _ in METRICS},
            }

    paired = {}
    if len(schedulers) > 1:
        base = schedulers[0]
        by = {(r["point"], r["index"], r["scheduler"]): r for r in rows}
        for s in schedulers[1:]:
            for p in points:
                c = {"both": 0, "identical": 0, "fewer": 0, "same": 0, "more": 0, "diff": []}
                for r in groups.get((p, s), []):
                    b = by.get((p, r["index"], base))
                    if not b or r["success"] != "1" or b["success"] != "1":
                        continue
                    c["both"] += 1
                    c["identical"] += r["schedule_hash"] == b["schedule_hash"]
                    x, y = int(r["total_job_preemptions"]), int(b["total_job_preemptions"])
                    c["fewer" if x < y else "same" if x == y else "more"] += 1
                    c["diff"].append(x - y)
                paired[s, p] = c
    return {"rows": rows, "schedulers": schedulers, "points": points, "axes": axes, "cell": cell,
            "paired": paired}


# ------------------------------------------------------------------ HTML
def _pct(x):
    return "–" if x is None else f"{100 * x:.1f}%"


def _num(mu, ci):
    if mu is None:
        return "–"
    digits = 3 if abs(mu) < 100 else 1
    return f"{mu:.{digits}f}" + (f" <span class=ci>± {ci:.{digits}f}</span>" if ci else "")


def _chart(title, ylabel, series, xlabel, percent=False):
    """series: [(scheduler, slot, [(x, y)])]. Line chart, one y-axis, hover = native tooltip."""
    pts = [(x, y) for _, _, xy in series for x, y in xy if y is not None]
    if not pts:
        return ""
    W, H, L, R, T, B = 600, 280, 56, 120, 16, 40
    xs = sorted({x for x, _ in pts})
    x0, x1 = xs[0], xs[-1]
    y0 = 0.0
    y1 = max(y for _, y in pts)
    y1 = 1.0 if percent else (y1 * 1.1 if y1 > 0 else 1.0)
    sx = (lambda x: L + (x - x0) / (x1 - x0) * (W - L - R)) if x1 > x0 else (lambda x: L + (W - L - R) / 2)
    sy = lambda y: T + (1 - (y - y0) / (y1 - y0)) * (H - T - B)  # noqa: E731
    ends = []
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">']
    for k in range(5):
        v = y0 + (y1 - y0) * k / 4
        y = sy(v)
        lab = f"{100 * v:.0f}%" if percent else f"{v:.3g}"
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}"/>'
                     f'<text class="tick" x="{L - 6}" y="{y + 4:.1f}" text-anchor="end">{lab}</text>')
    step = max(1, len(xs) // 8)
    for x in xs[::step]:
        parts.append(f'<text class="tick" x="{sx(x):.1f}" y="{H - B + 16}" text-anchor="middle">{x:g}</text>')
    parts.append(f'<text class="axis" x="{(L + W - R) / 2:.0f}" y="{H - 6}" text-anchor="middle">{xlabel}</text>')
    for name, slot, xy in series:
        xy = [(x, y) for x, y in sorted(xy) if y is not None]
        if not xy:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(xy))
        parts.append(f'<path class="line s{slot}" d="{d}"/>')
        for x, y in xy:
            val = f"{100 * y:.1f}%" if percent else f"{y:.4g}"
            parts.append(f'<g class="pt"><circle class="dot s{slot}" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4"/>'
                         f'<circle class="hit" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="10">'
                         f'<title>{html.escape(name)} · {xlabel} {x:g}: {val}</title></circle></g>')
        if len(series) <= 4:                     # direct label at the line end
            ends.append((sy(xy[-1][1]), sx(xy[-1][0]), name))
    # end labels, pushed apart vertically so that equal ends stay readable
    ends = [list(e) for e in sorted(ends)]
    for k in range(1, len(ends)):
        ends[k][0] = max(ends[k][0], ends[k - 1][0] + 13)
    for y, x, name in ends:
        parts.append(f'<text class="end" x="{x + 8:.1f}" y="{y + 4:.1f}">{html.escape(name)}</text>')
    parts.append("</svg>")
    return (f'<figure class="fig"><figcaption>{html.escape(title)} <span class=muted>({html.escape(ylabel)})'
            f'</span></figcaption>{"".join(parts)}</figure>')


def _legend(schedulers):
    return '<div class="legend">' + "".join(
        f'<span><i class="sw s{i % len(SERIES)}"></i>{html.escape(s)}</span>' for i, s in enumerate(schedulers)) + "</div>"


def write_report(folder, path=None, x="auto") -> Path:
    folder = Path(folder)
    S = summarize(folder, x)
    scheds, points, axes, cell = S["schedulers"], S["points"], S["axes"], S["cell"]
    slot = {s: i % len(SERIES) for i, s in enumerate(scheds)}
    meta = {}
    if (folder / "meta.json").exists():
        meta = json.loads((folder / "meta.json").read_text())
    name = meta.get("name", folder.name)

    # headline: success over everything
    head = []
    for s in scheds:
        cs = [cell[p, s] for p in points]
        sets, ok = sum(c["sets"] for c in cs), sum(c["ok"] for c in cs)
        head.append(f'<div class="stat"><div class="k"><i class="sw s{slot[s]}"></i>{html.escape(s)}</div>'
                    f'<div class="v">{_pct(ok / sets if sets else None)}</div>'
                    f'<div class="muted">success · {ok}/{sets} runs</div></div>')

    # curves per group (n, m) when the x axis has >= 2 values
    groups = defaultdict(list)
    for p in points:
        groups[axes[p][0]].append(p)
    charts = []
    for g, ps in groups.items():
        if len(ps) < 2:
            continue
        xlabel = axes[ps[0]][1]
        figs = [_chart("Success ratio", "share of sets", [(s, slot[s], [(axes[p][2], cell[p, s]["success"])
                                                                         for p in ps]) for s in scheds],
                       xlabel, percent=True)]
        for lab, col, _ in METRICS[:4]:
            figs.append(_chart(lab, "mean over successful runs",
                               [(s, slot[s], [(axes[p][2], cell[p, s]["metrics"][col][0]) for p in ps])
                                for s in scheds], xlabel))
        charts.append(f'<section class="card"><h2>{html.escape(g)}</h2>{_legend(scheds)}'
                      f'<div class="figs">{"".join(f for f in figs if f)}</div>'
                      f'<p class="note">Hover a point for its value. Schedulers with equal values draw '
                      f'on top of each other (the last one in the legend is visible).</p></section>')

    # success table
    th = "".join(f'<th><i class="sw s{slot[s]}"></i>{html.escape(s)}</th>' for s in scheds)
    body = []
    for p in points:
        c0 = cell[p, scheds[0]]
        tds = "".join(f'<td title="feasible sets: {_pct(cell[p, s]["success_feasible"])}">'
                      f'{_pct(cell[p, s]["success"])}</td>' for s in scheds)
        extra = f' <span class=muted>({c0["gen_err"]} not generated)</span>' if c0["gen_err"] else ""
        body.append(f"<tr><th>{html.escape(p)}{extra}</th><td>{c0['sets']}</td>"
                    f"<td>{c0['feasible']}</td>{tds}</tr>")
    success_table = (f'<table><thead><tr><th>Point</th><th>Sets</th><th>Feasible</th>{th}</tr></thead>'
                     f'<tbody>{"".join(body)}</tbody></table>')

    # metrics table: one block per metric
    mblocks = []
    for lab, col, lower in METRICS:
        trs = []
        for p in points:
            vals = [cell[p, s]["metrics"][col][0] for s in scheds]
            best = min((v for v in vals if v is not None), default=None) if lower else None
            tds = "".join(
                f'<td class="{"best" if v is not None and v == best and len(scheds) > 1 else ""}">'
                f'{_num(*cell[p, s]["metrics"][col][:2])}</td>' for s, v in zip(scheds, vals))
            trs.append(f"<tr><th>{html.escape(p)}</th>{tds}</tr>")
        mblocks.append(f'<h3>{html.escape(lab)}</h3><table><thead><tr><th>Point</th>{th}</tr></thead>'
                       f'<tbody>{"".join(trs)}</tbody></table>')

    # paired comparison
    paired_html = ""
    if S["paired"]:
        base = scheds[0]
        blocks = []
        for s in scheds[1:]:
            trs = []
            for p in points:
                c = S["paired"][s, p]
                n = c["both"] or 1
                mu, ci, _ = _mean_ci(c["diff"])
                trs.append(f"<tr><th>{html.escape(p)}</th><td>{c['both']}</td>"
                           f"<td>{_pct(c['identical'] / n if c['both'] else None)}</td>"
                           f"<td>{c['fewer']}</td><td>{c['same']}</td><td>{c['more']}</td>"
                           f"<td>{_num(mu, ci)}</td></tr>")
            blocks.append(f'<h3>{html.escape(s)} vs {html.escape(base)}</h3><table><thead><tr><th>Point</th>'
                          f'<th>Both succeed</th><th>Identical schedule</th><th>Fewer preemptions</th>'
                          f'<th>Same</th><th>More</th><th>Mean difference</th></tr></thead>'
                          f'<tbody>{"".join(trs)}</tbody></table>')
        paired_html = (f'<section class="card"><h2>Paired comparison, same sets</h2>{"".join(blocks)}'
                       f'<p class="note">Sets where both schedulers succeed. Preemptions: total job preemptions '
                       f'over the horizon; difference = {html.escape("scheduler − " + base)}.</p></section>')

    # failures
    fails = defaultdict(lambda: defaultdict(int))
    for p in points:
        for s in scheds:
            for st, k in cell[p, s]["status"].items():
                if st != "ok":
                    fails[s][st] += k
    if fails:
        trs = "".join(f"<tr><th>{html.escape(s)}</th><td>{html.escape(st)}</td><td>{k}</td></tr>"
                      for s, d in fails.items() for st, k in sorted(d.items()))
        fail_html = (f'<section class="card"><h2>Failed runs</h2><table><thead><tr><th>Scheduler</th>'
                     f'<th>Status</th><th>Runs</th></tr></thead><tbody>{trs}</tbody></table>'
                     f'<p class="note">Systems in {html.escape(str(folder / "failures"))}. Replay: '
                     f'<code>unifsim simulate &lt;file&gt; --scheduler &lt;name&gt; --gantt</code></p></section>')
    else:
        fail_html = '<section class="card"><h2>Failed runs</h2><p>None: every run met every deadline and passed the validator.</p></section>'

    sess = meta.get("sessions", [])
    commit = next((x.get("git_commit") for x in reversed(sess) if x.get("git_commit")), None)
    css_slots = "".join(f".s{i}{{--c:{lt}}}" for i, (lt, _) in enumerate(SERIES))
    css_dark = "".join(f".s{i}{{--c:{dk}}}" for i, (_, dk) in enumerate(SERIES))
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(name)} · campaign</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --ink:#1d2330; --muted:#667085; --line:#e4e7ec; --accent:#2e5bba; }}
{css_slots}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0f1218; --card:#171b23; --ink:#e7eaf0; --muted:#98a2b3; --line:#2a303c; --accent:#7aa2ff; }}
  {css_dark} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 -apple-system, "Segoe UI", Inter, Roboto, sans-serif; }}
main {{ max-width:1180px; margin:0 auto; padding:28px 16px 48px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:0 0 12px; }} h3 {{ font-size:13px; margin:16px 0 6px; color:var(--muted); }}
.muted, .ci {{ color:var(--muted); }} .ci {{ font-size:12px; }}
.sub-title {{ color:var(--muted); margin:0 0 20px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; margin-bottom:16px; overflow-x:auto; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px; margin-bottom:16px; }}
.stat {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
.stat .k {{ font-weight:600; }} .stat .v {{ font-size:26px; font-weight:700; font-variant-numeric:tabular-nums; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th, td {{ padding:5px 10px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }}
th:first-child {{ text-align:left; }}
thead th {{ color:var(--muted); font-weight:600; font-size:12px; }}
tbody th {{ font-weight:500; }}
td.best {{ font-weight:700; color:var(--accent); }}
.sw {{ display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; vertical-align:-1px; background:var(--c); }}
.legend {{ display:flex; flex-wrap:wrap; gap:14px; margin:0 0 8px; color:var(--ink); font-size:13px; }}
.figs {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(420px, 1fr)); gap:8px 20px; }}
@media (max-width:520px) {{ .figs {{ grid-template-columns:1fr; }} }}
.fig {{ margin:0; }} .fig figcaption {{ font-weight:600; font-size:13px; margin:6px 0 2px; }}
.chart {{ width:100%; height:auto; display:block; }}
.chart .grid {{ stroke:var(--line); }} .chart .tick, .chart .axis {{ fill:var(--muted); font-size:11px; }}
.chart .line {{ fill:none; stroke:var(--c); stroke-width:2; stroke-linejoin:round; }}
.chart .dot {{ fill:var(--c); stroke:var(--card); stroke-width:2; }}
.chart .hit {{ fill:transparent; }} .chart .pt:hover .dot {{ r:6; }}
.chart .end {{ fill:var(--ink); font-size:11px; }}
.note {{ color:var(--muted); font-size:12px; margin-top:8px; }}
code {{ font-family:ui-monospace, monospace; font-size:12px; }}
</style></head><body><main>
<h1>{html.escape(name)}</h1>
<p class="sub-title">{len(points)} point(s) · {len(scheds)} scheduler(s) · {len(S["rows"])} rows ·
report {datetime.now():%Y-%m-%d %H:%M}{" · commit " + html.escape(commit[:12]) if commit else ""}</p>
<div class="stats">{"".join(head)}</div>
{"".join(charts)}
<section class="card"><h2>Success ratio per point</h2>{success_table}
<p class="note">Success = every deadline met and the trace passes the independent validator.
Hover a cell: success over the feasible sets only (Horváth).</p></section>
<section class="card"><h2>Metrics (mean ± 95% CI over successful runs)</h2>{"".join(mblocks)}
<p class="note">Bold: lowest mean of the row.</p></section>
{paired_html}
{fail_html}
</main></body></html>"""
    path = Path(path) if path else folder / "report.html"
    path.write_text(page, encoding="utf-8")
    return path
