# unifsim — user guide

unifsim simulates real-time scheduling algorithms on **uniform multiprocessor
platforms**, with **exact arithmetic**, and checks every schedule it produces.

Contents

1. [Principle](#1-principle)
2. [Install](#2-install)
3. [Quick start](#3-quick-start)
   - [Command line](#3b-command-line)
4. [Describing a system](#4-describing-a-system)
   - [Generating task sets](#4b-generating-task-sets)
5. [Available algorithms](#5-available-algorithms)
6. [Reading the result: the trace](#6-reading-the-result-the-trace)
7. [Validation](#7-validation)
8. [Metrics](#8-metrics)
9. [Comparing algorithms (HTML report)](#9-comparing-algorithms-html-report)
10. [Writing your own algorithm](#10-writing-your-own-algorithm)
11. [Project layout](#11-project-layout)
12. [Tests](#12-tests)
13. [Limits](#13-limits)

---

## 1. Principle

Each part has one job, and no part trusts another:

```
System ──► Engine ⇄ Scheduler          the scheduler only decides who runs where
              │
              ▼
            Trace ──► validate()        checks the schedule from the trace alone
              │
              └─────► compute_metrics() measures from the trace alone
```

- The **scheduler** answers one question: *at time t, which job runs on which processor?*
- The **engine** owns time. It releases jobs, asks the scheduler, executes the
  decision exactly until the next event, and records what ran in the **trace**.
- The **validator** recomputes every job from the tasks and checks the trace
  without reusing any engine code. A bug in the engine or in an algorithm cannot
  hide itself.
- The **metrics** (preemptions, migrations, response times) are computed from the
  trace, with the same definitions and names as shrimp.

All numbers are `int` or `Fraction`. Floats are refused: there is no rounding and
no epsilon anywhere.

## 2. Install

Python ≥ 3.10.

```bash
git clone https://github.com/yahyahamdani1996-cmyk/Unifsim.git
cd Unifsim
python -m venv venv            # on Ubuntu: python3 -m venv venv
source venv/bin/activate
pip install -e ".[test]"
pytest -q                      # all tests must pass
```

Each new session: `cd Unifsim && source venv/bin/activate && git pull`.

## 3. Quick start

```python
from unifsim import Task, Platform, System, run, compare

system = System(
    tasks=(Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4),     # Task(id, C, T)
           Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
    platform=Platform((6, 3, 2, 2, 1)),                      # speeds, fastest first
)

r = run(system, "pcg_star")     # simulate + validate + metrics (raises if anything is wrong)
r.schedule()                    # print the schedule
r.report()                      # print the metrics
r.trace, r.metrics              # the objects, for your own code

compare(system, ["pcg_star", "wc_pcg_star", "g_edf"], "report.html")   # HTML report
```

`run` also accepts a scheduler object: `run(system, MyPCGStar())`. The lower-level
functions (`simulate`, `validate`, `compute_metrics`) are described below.

Ready-made scripts, run from the repository root:

| Script | What it does |
|---|---|
| `python examples/running_example.py` | the paper's running example (Tables 2 and 3) under PCG\* |
| `python examples/compare_example.py` | PCG\* vs WC-PCG\* vs G-EDF, opens the HTML report |
| `python examples/simulate_example.py` | a 3-task system under PCG\* and G-EDF |

## 3b. Command line

```bash
unifsim list                                                          # available schedulers

# one system, one scheduler: validation + metrics
unifsim simulate Tasksets/m8_n20_U18/ts_0000.json --scheduler pcg_star
unifsim simulate --platform 8,6,5,4,3,2,1,1 --n 20 --U 18 --scheduler pcg_star     # no file needed
unifsim simulate --m 8 --n 20 --load 0.67 --index 3 --scheduler wc_pcg_star        # random platform
unifsim simulate ... --schedule                # also print the schedule
unifsim simulate ... --gantt                   # Gantt + metrics in the browser
unifsim simulate ... --gantt --out runs/a.html # same, file kept
unifsim simulate ... --json metrics.json       # metrics as JSON
unifsim simulate ... --horizon 120             # longer than the hyperperiod

# one system, several schedulers: table in the terminal + HTML report
unifsim compare Tasksets/m8_n20_U18/ts_0000.json --schedulers pcg_star,wc_pcg_star,g_edf
unifsim compare --platform 6,3,2,2,1 --n 6 --U 10 --schedulers pcg_star,wc_pcg_star --out r.html --no-open
```

- Charts: mouse wheel to zoom, drag to move, double-click to reset, or type a
  from / to time window; the window is shared by all charts of a report.
- HTML reports go to `unifsim_reports/` in the current folder by default (ignored
  by git, only the 20 most recent kept; `UNIFSIM_REPORTS=dir` to change it). Not
  `/tmp`: Firefox installed as a snap cannot read it. `--out FILE.html` keeps a
  report where you choose, `--no-open` does not open the browser.
- `--tikz FILE.tex` is reserved for the LaTeX export of schedules (papers, thesis);
  it is refused until implemented (`src/unifsim/export/tikz.py`).

- A system is a JSON file **or** the generator options (`--platform`/`--m`, `--n`,
  `--U`/`--load`, `--index`, default 0). The options give exactly the set that
  `unifsim gen` would write (`--index 3` = `ts_0003.json`).
- `simulate` and `compare` take one system. A folder is refused: many systems is a
  campaign.
- `simulate` exits with code 1 if the scheduler fails (deadline miss, invalid
  decision or schedule) and prints why.
- `--arrivals periodic` is the default and the only model for now.

## 4. Describing a system

### Task

```python
Task(id, C, T)            # implicit deadline, D = T
Task(id, C, T, D=d)       # constrained deadline (not supported by TL-plane algorithms yet)
```

- `C` is the **work at speed 1**. On a uniform platform `C > T` is valid
  (`u = C/T` can be up to the fastest speed).
- `T` and `D` are integers. `C` is `int`, `Fraction` or a string such as `"7/2"`.
- `task.u` gives the utilization, exactly.

### Platform

```python
Platform((6, 3, 2, 2, 1))     # speeds sorted fastest first; index 0 = fastest
```

Convention for examples: the slowest processor has speed 1.

### System

```python
system = System(tasks=(...), platform=Platform(...))
system.U                    # total utilization (exact)
system.hyperperiod          # lcm of the periods = default simulation length
system.horvath_feasible()   # exact feasibility test (implicit deadlines)
system.jobs(horizon)        # all jobs released before horizon
```

`horvath_feasible()` checks, with utilizations sorted non-increasingly,
`u(1) + … + u(k) ≤ S_k` for `k < m` and `U ≤ S_m` (Horváth; Funk, Goossens,
Baruah, RTSS 2001). On a feasible system, an optimal algorithm must never miss a
deadline: if it does, it is a bug.

### Saving and loading a system

```python
system.save("examples/my_system.json")
system = System.load("examples/my_system.json")
system.hash                 # SHA-256 of the canonical form: identifies the system
```

```json
{
  "format_version": 1,
  "speeds": ["6", "3", "2", "2", "1"],
  "tasks": [{"id": 1, "C": "33", "T": 8, "D": 8}, ...]
}
```

Fractions are written as strings, so files are exact.

### Exact numbers

```python
from fractions import Fraction as F
Task(0, F(7, 2), 4)    # ok
Task(0, "7/2", 4)      # ok
Task(0, 3.5, 4)        # TypeError: float rejected
```

## 4b. Generating task sets

Requires `pip install -e ".[gen]"` (numpy and ConvolutionalFixedSum, pinned version).

### From the command line

Two platform modes; give one of `--platform` / `--m`, and one of `--U` / `--load`.

```bash
# fixed platform (same speeds for every set), absolute utilization
unifsim gen --platform 8,6,5,4,3,2,1,1 --n 20 --U 18 --count 1000
#   -> Tasksets/m8_n20_U18/ts_0000.json ... ts_0999.json

# random platform: m and n fixed, for EACH set the speeds and the tasks are drawn
unifsim gen --m 8 --n 20 --load 0.67 --count 1000
#   -> Tasksets/m8_n20_load0.67/ts_0000.json ...      U = 0.67 x S_m of each platform

unifsim gen --platform 8,6,5,4,3,2,1,1 --n 8-40/4 --U 6-30 --count 1000   # every (n, U) pair
unifsim gen --platform 8,6,5,4,3,2,1,1 --n 20 --U 18 --index 417          # only set 417
unifsim gen --m 8 --n 20 --load 0.67 --count 1000 --bank                   # one .jsonl.gz per point
unifsim gen --help                                                          # all options
```

- Random platform: integer speeds drawn uniformly in `--speeds 1-10` (default), the
  slowest forced to 1, sorted fastest first. Each file holds its own platform.
- With a fixed platform, `--load` also works (U = load × S_m).
- Tasks are sorted by non-increasing utilization (task 0 = largest), as in the paper.
- Defaults: periods `2,3,4,5,6,10,12,15,20,30,60`, `u_min 1/100`, `u_max` = fastest
  speed of the platform, quantum `1/10000`.
- Ranges: `20`, `8,12,20`, `6-30` (step 1), `8-40/4` (step 4), `0.1-1/0.1`; fractions allowed.
- The same command always produces the same sets; `--seed` only draws another family.
- Existing files are kept: rerun the same command to resume.
- Parallel (`--jobs`, default: all cores).

Use a generated set like any other: `run(System.load("Tasksets/m8_n20_U18/ts_0417.json"), "pcg_star")`.

### One set from Python

```python
from unifsim.gen import cfs_uniform
from unifsim import Platform

system = cfs_uniform(n=20, U=18, platform=Platform((8, 6, 5, 4, 3, 2, 1, 1)),   # fixed platform
                     periods=(2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60),
                     u_min="1/100", u_max=8, quantum="1/10000", seed=42)
system.save("examples/dev_n20_U18_s42.json")      # keep it for development
```

Method (`cfs_uniform@1`, from shrimp `generate_task.py`): utilizations drawn
uniformly in `[u_min, u_max]^n` summing to U (cfsa), quantized to multiples of
`quantum`, rejected unless the Horváth conditions hold, periods drawn from
`periods`, `C = u·T`.

| Option | Default | shrimp behaviour |
|---|---|---|
| `seed` | required for reproducibility | unseeded |
| `rounding` | `"exact_sum"`: the quantized utilizations sum to U exactly | `"independent"`: each u rounded alone, the sum may differ from U |
| `order` | `"sorted"`: task 0 = largest utilization (as shrimp and the paper) | same |

Same arguments and seed → same set, on any machine. `system.meta` records the
generator and its version, the parameters, the seed, the number of attempts, the
utilization reached and `max_task_share` (largest u / U, to track skewed sets).

### Campaign points

```python
from unifsim.gen import point, regenerate

for s in point(n=20, U=18, count=1000, master_seed=2027, platform=..., periods=...):
    ...                                           # fixed platform, generated in memory
for s in point(n=20, load="0.67", count=1000, master_seed=2027, m=8, speed_range=(1, 10), periods=...):
    ...                                           # random platform per set
s = regenerate(n=20, U=18, index=417, master_seed=2027, platform=..., periods=...)
```

Set `i` of a point is generated from `derive_seed(master_seed, n, U, i)` (SHA-256),
so it does not depend on the order of generation or on the number of workers,
and any line of a result file can be regenerated alone.

Generation is dominated by cfsa (about 0.27 s per set at n = 40): a campaign
should generate each set once and run all the algorithms on it.

### Banks

```python
from unifsim.gen import write_bank, read_bank
write_bank("bank/n20_U18.jsonl.gz", point(...))   # freeze a point (one set per line, gzip)
for s in read_bank("bank/n20_U18.jsonl.gz"): ...  # checks every stored hash
```

Rule: seeds to work, a frozen bank for anything published or shared. A seed only
regenerates the same set as long as the code and its dependencies do not change;
the hash stored with each set detects any difference.

### Arrivals

`simulate(..., arrivals=Periodic())` is the default (synchronous periodic). The
arrival model is separate from the System so the same System can later be run
with sporadic arrivals; only `Periodic` exists in v1.

## 5. Available algorithms

`make(name)` builds an algorithm from its name. The same names are used in the
report and, later, in campaigns.

| Name | Algorithm | Family |
|---|---|---|
| `pcg_star` | PCG\* with the DP-fair allocation (b = u·Δ) | deadline-partitioned (DP) |
| `wc_pcg_star` | WC-PCG\*: PCG\* with the work-conserving (WK) allocation, jobs taken by non-decreasing remaining work (the order of the paper) | DP |
| `wc_pcg_star_idx` | WC-PCG\* with jobs taken by task index | DP |
| `pcg_star_online` | PCG\* decided online at every scheduling point (port of shrimp `pcg_etoile_tl`), DP-fair allocation | DP (`DPOnline`) |
| `wc_pcg_star_online` | same, WK allocation | DP (`DPOnline`) |
| `pcg_star_v2` | PCG\* with all the events of an instant handled together (Algorithms 1–2 of the ECRTS paper), DP-fair allocation | DP |
| `wc_pcg_star_v2` | same, WK allocation | DP |
| `g_edf` | Global EDF: earliest deadline on the fastest processor | global, not optimal for m > 1 |

`pcg_star` computes each TL-plane at its start (reference implementation);
`pcg_star_online` decides at every scheduling point (shrimp). They differ through
three handling rules: see [PCG_ONLINE_VS_REFERENCE.md](PCG_ONLINE_VS_REFERENCE.md).

### Terminology

- **DP** (deadline partitioning): time is cut into TL-planes at every deadline;
  inside each plane, each job receives a budget, and a local algorithm schedules
  the budgets.
- **DP-fair allocation**: budget = u·Δ (Levin et al., RTSS 2010). DP + DP-fair
  allocation = a DP-fair algorithm (PCG\*).
- **WK allocation**: start from the lag lower bound
  `b_inf = max(0, rem − u(d − t1))`, then give the remaining capacity of the plane
  to the jobs while the Horváth conditions of the plane hold. WC-PCG\* = DP + WK
  allocation; it is not DP-fair.

### Building an algorithm by hand

```python
from unifsim.schedulers.dp import PCGStar
from unifsim.schedulers.dp.budgets import dp_fair, greedy_wk

PCGStar()                                 # = make("pcg_star")
PCGStar(budget=greedy_wk("remaining"))    # = make("wc_pcg_star")
PCGStar(budget=greedy_wk("index"))        # = make("wc_pcg_star_idx")
PCGStar(budget=greedy_wk("remaining", epsilon=Fraction(1, 1250)))   # shrimp's stopping threshold
```

`epsilon` is 0 by default: in exact arithmetic any residual capacity is real
capacity. shrimp stopped when the residual was below `epsilon · Δ`.

## 6. Reading the result: the trace

`simulate` returns a `Trace`, i.e. the schedule:

```python
trace.segments    # list of Segment: who ran where, from when to when
trace.planes      # TL-planes and budgets (DP algorithms only, [] otherwise)
trace.horizon     # end of the simulation
```

A `Segment` has four fields:

```python
s.proc      # processor index, 0 = fastest
s.job       # the job: s.job.name ("T1_0" = first job of task 1), s.job.task_id, s.job.k,
            #          s.job.release, s.job.deadline, s.job.C
s.start     # start time (Fraction)
s.end       # end time (Fraction)
```

Consecutive pieces of the same job on the same processor are merged into one
segment.

A `PlaneRecord` (element of `trace.planes`) has `t0`, `t1` and `budgets`, a tuple
of `(job, budget)`.

Simulation length: the hyperperiod by default, or `simulate(system, algo, horizon=20)`.

## 7. Validation

`validate(system, trace)` returns nothing if the schedule is correct and raises
`ValidationError` otherwise. The error carries the code of the broken rule:

| Code | Rule |
|---|---|
| V0 | every segment refers to an existing job and processor |
| V1 | 0 ≤ start < end ≤ horizon |
| V2 | no processor runs two jobs at the same time |
| V3 | no job runs on two processors at the same time |
| V4 | no job runs before its release |
| V5 | every job with deadline ≤ horizon executes exactly C (duration × speed) |
| V6 | every job with deadline ≤ horizon completes by its deadline |
| V7 | every such job appears in the trace |

Example of a failure: `ValidationError: [V5] (1, 0) executed 2, expected C=33`.

Errors raised during the simulation itself:

| Exception | Meaning |
|---|---|
| `DeadlineMiss` | a job reaches its deadline with work left (e.g. G-EDF at full load) |
| `InvalidDecision` | the algorithm returned an impossible decision (job on two processors, unknown processor, …) |
| `BudgetInfeasible` | a DP allocation produced budgets that cannot fit in the plane |

## 8. Metrics

```python
m = compute_metrics(system, trace)
print(m.report())           # terminal table
m.total_job_preemptions     # any field below
m.as_row()                  # dict with shrimp column names (for CSV / campaigns)
```

### Definitions

For each job, its execution pieces in time order:

- **preemption**: between two consecutive pieces, there is a gap or a processor
  change (completing is not a preemption);
- **migration**: a piece starts on a processor different from the previous one;
- **local**: both pieces are in the same TL-plane (pieces are first cut at plane
  boundaries); **boundary** = total − local. Only for DP algorithms (`None`, shown
  as `–`, otherwise);
- **task migrations**: processor changes over the pieces of all jobs of a task;
  **boundary task migrations** = task migrations − job migrations, i.e. processor
  changes between two successive jobs;
- **response time ratio** of a completed job: (completion − release) / D.

| Field | Meaning |
|---|---|
| `total_job_preemptions`, `local_…`, `boundary_…` | preemptions |
| `total_job_migrations`, `local_…`, `boundary_…` | job migrations |
| `total_task_migrations`, `total_boundary_task_migrations` | task migrations |
| `avg_/worst_/best_response_time_ratio` | mean / max / min of R/D over all completed jobs |
| `avg_/worst_/best_response_time_ratio_per_task` | mean R/D of each task, then mean / max / min over the tasks |
| `n_jobs_released`, `n_jobs_completed` | number of jobs |
| `per_job_value(name)` | a counter divided by the number of jobs released |
| `per_job` | `{job: (preemptions, migrations)}` |
| `per_plane_preemptions` | `[(t0, t1, local preemptions)]`, e.g. to check the 2(m−1) bound |

These definitions are those of shrimp (`Simulator.log_results`, `Job.py`,
`Task.py`). On the running example, all values are equal to the shrimp logs for
PCG\*, WC-PCG\* (remaining-time order) and WC-PCG\* (index order); the tests check it.

The `_per_job` divisor (jobs released) is still to be confirmed against shrimp's
`watch_campaign_metrics.py`.

## 9. Comparing algorithms (HTML report)

```python
from unifsim.gui import compare
compare(system, ["pcg_star", "wc_pcg_star", "g_edf"], "report.html", title="My system")
```

Open `report.html` in a browser. The page contains:

- the system (tasks and their colors);
- the metrics, one column per algorithm, the best value of each row in bold
  (lower is better);
- one Gantt chart per algorithm, all on the same time scale; TL-plane boundaries
  dashed; hover a block for job, processor, interval and work.

An algorithm that fails (deadline miss, invalid decision, validation error) is
shown as `failed` with its error; the others are still displayed.

To get one algorithm's result without a page: `from unifsim.gui import run;
run(system, "pcg_star")` returns `{"trace", "metrics", "error"}`.

## 9b. Campaigns

A campaign runs several algorithms on the **same** reproducible task sets over a grid
of parameters and writes one CSV row per (set, algorithm). Design:
[CAMPAIGN_DESIGN.md](CAMPAIGN_DESIGN.md).

```bash
unifsim campaign campaigns/pcg_star_v1_v2.toml        # run; rerun the same command to resume
unifsim campaign report results/pcg_star_v1_v2        # HTML report (results/<name>/report.html)
```

The spec file (TOML):

```toml
name       = "pcg_star_v1_v2"                 # results/<name>/
schedulers = ["pcg_star", "pcg_star_v2"]      # one or more, all on the same sets
count      = 100                              # sets per grid point
seed       = 2026

[grid]                                        # cartesian product, same options as `unifsim gen`
n      = [8, 16]                              # or "8-40/4"
m      = [4, 8]                               # random platform per set (or platform = "8,6,5,4,3,2,1,1")
speeds = "1-10"
load   = "0.5-1/0.1"                          # or U = "6-30" with a fixed platform

[generator]                                   # optional, defaults of `unifsim gen`
periods = [2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60]

# tasksets = "Tasksets/m8_n20_U18"            # instead of [grid]: run on existing `unifsim gen` files
```

- **Same sets as `unifsim gen`**: a point `m8_n20_U18` with the same seed and options
  gives exactly the sets of `Tasksets/m8_n20_U18/`, generated on the fly.
- **Success**: every row has `success` (1/0) and `status`: `ok`, `deadline_miss`
  (`miss_time`, `miss_job`), `budget_infeasible`, `invalid_decision`, `invalid_trace`,
  `error`; `generation_error` when a set cannot be drawn (no run, `success` empty).
  `feasible` is the Horváth test of the set. Metrics only for successful runs.
- **Failed runs** are saved in `results/<name>/failures/` and replayed with
  `unifsim simulate <file> --scheduler <name> --gantt`.
- **Resume / extend**: rerun the same command; done rows are skipped. `count`,
  `schedulers` and `description` may change between runs (to extend a campaign);
  any other change is refused (use another name, or `--restart`).
- `--jobs N` workers (default: all cores); `--out DIR` results root (default `results`).
- Columns: key (`point, n, m, U, load, index, system_hash, scheduler`), outcome, then the
  metrics with their shrimp names, exact (`37/5`), plus `_float` columns for plots
  (pgfplots reads the CSV directly). `schedule_hash` identifies the schedule, so
  identical schedules of two algorithms can be counted.
- The report gives success ratios (all sets, feasible sets), means ± 95% CI, curves vs
  U or load, and a paired comparison with the first scheduler (identical schedules,
  fewer / same / more preemptions on the same sets).

## 10. Writing your own algorithm

There are three cases. In all of them the engine, the validator, the metrics and
the report work unchanged.

### a) A global algorithm: write `decide`

```python
# src/unifsim/schedulers/global_/my_algo.py
from ..base import Decision, Scheduler


class MyAlgo(Scheduler):
    name = "my_algo"

    def decide(self, t, view):
        # view.active       : active jobs (released, not completed)
        # view.remaining(j) : remaining work of job j
        # view.platform     : speeds, m
        order = sorted(view.active, key=lambda j: (j.deadline, j.task_id))
        assignment = {p: j for p, j in enumerate(order[:view.platform.m])}
        return Decision(assignment=assignment, wake_at=None)
```

- `assignment`: `{processor index: job}`; a missing processor is idle.
- `wake_at`: an instant `> t` where you want to be called again, in addition to
  releases, completions and deadlines (e.g. when two laxities cross). `None` if
  not needed.

### b) A TL-plane (DP) algorithm: write `schedule_plane`

The class `DP` already cuts time into planes, computes and checks the budgets,
replays your plan and records the planes in the trace. You only schedule one plane.

```python
# src/unifsim/schedulers/dp/my_pcg.py
from fractions import Fraction
from .base import DP


class MyPCG(DP):
    name = "my_pcg"

    def schedule_plane(self, budgets, speeds, length):
        # budgets[i] > 0 : work of local job i in this plane
        # speeds         : non-increasing, speeds[0] = fastest
        # length         : the plane is [0, length)
        plan = [[] for _ in speeds]
        # ... plan[p].append((i, (start, end))) ...
        return plan
```

Each job `i` must execute exactly `budgets[i]` (duration × speed); times are
relative to the start of the plane. The building blocks of PCG\* (`Proc`, `LocalJob`,
`Event`, `assign`, `unassign`, `compute_next_event`, `flatten`) are in
`schedulers/dp/local/plane.py`, and `schedulers/dp/local/pcg_star.py` is a full
example.

### c) A new allocation: write a budget function

```python
def my_allocation(jobs, plane, scheduler, view):
    t0, t1 = plane
    return [ ... one budget per job, in the order of `jobs` ... ]

PCGStar(budget=my_allocation)
```

`schedulers/dp/budgets.py` contains `dp_fair`, `greedy_wk` and `bounds(job, …)`
(returns `b_inf, b_sup`).

### Then

1. Register it in `src/unifsim/schedulers/registry.py`:
   `REGISTRY["my_algo"] = MyAlgo`.
2. Test it:
   ```python
   trace = simulate(system, make("my_algo"))
   validate(system, trace)          # raises on the first broken rule
   ```
3. Compare it: `compare(system, ["pcg_star", "my_algo"], "report.html")`.

## 11. Project layout

```
Unifsim/
├── examples/                 scripts to run
├── campaigns/                campaign spec files (.toml)
├── docs/USER_GUIDE.md        this guide
├── src/unifsim/
│   ├── model/                Task, Job, Platform, System
│   ├── engine/               simulate(), errors
│   ├── schedulers/
│   │   ├── base.py           Scheduler, Decision, View
│   │   ├── registry.py       make(name)
│   │   ├── global_/          g_edf
│   │   └── dp/               DP base class, budgets (dp_fair, greedy_wk), PCGStar
│   │       └── local/        plane.py (building blocks), pcg_star.py
│   ├── trace/                Trace, Segment, PlaneRecord
│   ├── validate/             validate(), rules V0–V7
│   ├── metrics/              compute_metrics(), Metrics
│   ├── campaign/             spec (TOML), runner (rows.csv), report (HTML)
│   └── gui/                  compare(), run(): HTML report
└── tests/
    ├── unit/                 model, engine, DP, metrics, report
    ├── validator/            one corrupted trace per rule
    └── oracle/               comparison with the reference PCG implementation
```

## 12. Tests

```bash
pytest -q                       # everything
pytest tests/unit -v            # one folder
pytest -k metrics               # by name
```

`tests/oracle` compares PCG\* with the reference implementation of Bertout and
Richard (same segments on the paper instances and 150 random systems). It is
skipped unless that code is importable:

```bash
PYTHONPATH=/path/to/pcg-main/src:/path/to/pcg-main pytest tests/oracle
```

## 13. Limits

- Periodic, synchronous tasks. TL-plane algorithms need implicit deadlines (D = T).
- Uniform platforms only (one speed per processor).
- No preemption or migration overheads.
- The report is a static page: the system and the algorithms are chosen in the script.
- Not yet: sporadic arrivals (the arrival model and the campaign keys are in place, only `Periodic` exists), TikZ export.
