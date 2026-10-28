# unifsim

Exact, independently validated simulator for real-time scheduling on uniform
multiprocessor platforms (deadline-partitioned and global algorithms).

- Exact arithmetic: `int` and `Fraction` only, no epsilon, `float` rejected.
- The scheduler decides, the engine executes, the validator checks the trace
  without reusing engine code, the metrics are computed from the trace.

**Documentation: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)**

## Install

```bash
python -m venv venv && source venv/bin/activate
pip install -e ".[test,gen]"
pytest -q
```

## Quick start

```python
from unifsim import Task, Platform, System, run, compare

system = System(tasks=(Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4),
                       Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
                platform=Platform((6, 3, 2, 2, 1)))

r = run(system, "pcg_star")      # simulate + validate + metrics
r.report()
compare(system, ["pcg_star", "wc_pcg_star", "g_edf"], "report.html")
```

## Algorithms

`pcg_star` (DP-fair allocation), `wc_pcg_star` (WK allocation, remaining-time
order), `wc_pcg_star_idx` (WK allocation, index order), `pcg_star_online` /
`wc_pcg_star_online` (decided online, shrimp port), `pcg_star_v2` / `wc_pcg_star_v2`
(all the events of an instant together, Algorithms 1–2 of the paper), `g_edf`.

## Campaigns

```bash
unifsim campaign campaigns/pcg_star_v1_v2.toml      # run or resume
unifsim campaign report results/pcg_star_v1_v2      # HTML report
```

## Credits

The PCG\* local scheduler (`src/unifsim/schedulers/dp/local/`) is ported from the
reference PCG implementation by Antoine Bertout and Pascal Richard; the WK
allocation and the metric definitions follow shrimp. `tests/oracle` checks the
port against the reference (skipped unless the reference package `pcg` is
importable):

```bash
PYTHONPATH=/path/to/pcg-main/src:/path/to/pcg-main pytest tests/oracle
```
