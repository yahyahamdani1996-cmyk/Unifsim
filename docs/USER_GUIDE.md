# unifsim — user guide

unifsim simulates real-time scheduling algorithms on **uniform multiprocessor
platforms**, with **exact arithmetic**, and checks every schedule it produces.

Contents

1. [Principle](#1-principle)
2. [Install](#2-install)
3. [Quick start](#3-quick-start)
4. [Describing a system](#4-describing-a-system)
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

Always the same four lines, whatever the system or the algorithm:

```python
from unifsim.model import Task, Platform, System
from unifsim.engine import simulate
from unifsim.schedulers.registry import make
from unifsim.validate import validate
from unifsim.metrics import compute_metrics

system = System(
    tasks=(Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4),     # Task(id, C, T)
           Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
    platform=Platform((6, 3, 2, 2, 1)),                      # speeds, fastest first
)

trace = simulate(system, make("pcg_star"))        # 1. run
validate(system, trace)                            # 2. check
for s in trace.segments:                           # 3. read the schedule
    print(s.proc, s.job.name, s.start, s.end)
print(compute_metrics(system, trace).report())     # 4. metrics
```

Ready-made scripts, run from the repository root:

| Script | What it does |
|---|---|
| `python examples/running_example.py` | the paper's running example (Tables 2 and 3) under PCG\* |
| `python examples/compare_example.py` | PCG\* vs WC-PCG\* vs G-EDF, opens the HTML report |
| `python examples/simulate_example.py` | a 3-task system under PCG\* and G-EDF |

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

## 5. Available algorithms

`make(name)` builds an algorithm from its name. The same names are used in the
report and, later, in campaigns.

| Name | Algorithm | Family |
|---|---|---|
| `pcg_star` | PCG\* with the DP-fair allocation (b = u·Δ) | deadline-partitioned (DP) |
| `wc_pcg_star` | WC-PCG\*: PCG\* with the work-conserving (WK) allocation, jobs taken by non-decreasing remaining work (the order of the paper) | DP |
| `wc_pcg_star_idx` | WC-PCG\* with jobs taken by task index | DP |
| `g_edf` | Global EDF: earliest deadline on the fastest processor | global, not optimal for m > 1 |

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
relative to the start of the plane. The building blocks of PCG\* (`Proc`, `Job`,
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
- Not yet: task-set generator, campaigns, sporadic tasks.
