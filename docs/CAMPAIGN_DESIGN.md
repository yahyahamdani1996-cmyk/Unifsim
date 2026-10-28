# `unifsim campaign`: design (to validate before coding)

## Purpose

Run several algorithms on the same, reproducible task sets over a grid of
parameters. Record **success** and the metrics of every run, without stopping on errors,
then analyse the rows separately.

```bash
unifsim campaign campaigns/pcg_star_v1_v2.toml          # run (or resume)
unifsim campaign report results/pcg_star_v1_v2/         # HTML report
```

## Spec file (TOML)

```toml
name       = "pcg_star_v1_v2"
schedulers = ["pcg_star", "pcg_star_v2"]   # 1 or more, all run on the same sets
count      = 1000                          # sets per grid point
seed       = 2026

[grid]                                     # cartesian product of the lists
n        = [8, 16, 32]                     # or "8-40/4"
# platform: exactly one of the two forms
platform = "8,6,5,4,3,2,1,1"               # fixed platform, every point
# m      = [4, 8, 16]                      # random platform per set...
# speeds = "1-10"                          # ...integer speeds, slowest = 1
# utilization: exactly one of the two forms
U        = "6-30"                          # fixed platform only
# load   = "0.5-1/0.05"                    # U = load x S_m

[generator]                                # same options and defaults as `unifsim gen`
periods = [2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60]
u_min   = "1/100"

[simulation]                               # reserved for sporadic tasks
arrivals = "periodic"                      # only value today
horizon  = "hyperperiod"                   # only value today

# tasksets = "Tasksets/m8_n16_U12"         # optional: use existing `unifsim gen` files instead
```

## What a run does

For each grid point, for each set index `0 .. count-1`:

1. generate the set (same function and seed derivation as `unifsim gen`, so the same set),
   or read it from `tasksets`;
2. run **every** scheduler on that set: simulation, then independent validation;
3. write one row per (set, scheduler).

The run never stops on a failed simulation, and it is resumable: rows already written are
skipped. It runs in parallel over the cores (`--jobs`, default: all), shows progress (points,
sets per second, time remaining), and is reproducible: the folder keeps the spec, the unifsim
version and the git commit.

## Success

Every row has a **`success`** column (1 or 0) and a **`status`** column that says why:

| status | success | meaning |
|---|---|---|
| `ok` | 1 | every deadline met and the trace passes the validator |
| `deadline_miss` | 0 | a job missed its deadline (`miss_time` and `miss_job` columns filled) |
| `budget_infeasible` | 0 | DP: the allocation gave budgets that fail Horváth in a plane |
| `invalid_decision` | 0 | the scheduler made an illegal decision (the engine refused it) |
| `invalid_trace` | 0 | the validator rejected the trace (a bug in an engine or a scheduler) |
| `error` | 0 | any other exception (message in `error`) |

- A `feasible` column (Horváth test on the set) lets the report give the success ratio **over
  feasible sets**: an optimal algorithm must reach 100%.
- The metrics are filled only when `success = 1`.
- Every failed system is saved in `failures/` with its scheduler, so it can be replayed with
  `unifsim simulate failures/<file>.json --scheduler <name> --gantt`.

## Output folder `results/<name>/`

```
rows.csv        one row per (set, scheduler)
spec.toml       copy of the spec
meta.json       unifsim version, git commit, start/end date, machine
failures/       failed systems (JSON)
```

`rows.csv` columns:

- **key:** `point` (e.g. `m8_n16_U12`), `n`, `m`, `U`, `load`, `index`, `system_hash`, `scheduler`;
- **outcome:** `success`, `status`, `feasible`, `miss_time`, `miss_job`, `error`, `runtime_s`;
- **metrics:** the shrimp names, exact (`37/5`), plus a float column for the ratios used in plots.

CSV because it opens in Excel and pandas, and pgfplots reads it directly (future TikZ figures).

## Report (`unifsim campaign report`)

Reads `rows.csv` only. For each point and each scheduler:

- **success ratio** (all sets, and feasible sets only);
- means and 95% confidence intervals of the metrics (successful runs);
- curves, e.g. success ratio or preemptions vs load, one curve per scheduler;
- with several schedulers, **paired comparison** set by set: fewer / same / more preemptions,
  identical schedules.

HTML first; LaTeX/pgfplots export later from the same rows.

## Not in v1

Sporadic arrivals and horizons other than the hyperperiod (keys reserved), TikZ export,
storing traces (any run can be regenerated from seed, point and index).
