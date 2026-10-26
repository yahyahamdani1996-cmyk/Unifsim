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
pip install -e ".[test]"
pytest -q
```

## Quick start

```python
from unifsim.model import Task, Platform, System
from unifsim.engine import simulate
from unifsim.schedulers.registry import make
from unifsim.validate import validate
from unifsim.metrics import compute_metrics

system = System(tasks=(Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4),
                       Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
                platform=Platform((6, 3, 2, 2, 1)))

trace = simulate(system, make("pcg_star"))
validate(system, trace)
print(compute_metrics(system, trace).report())
```

Compare algorithms in an HTML report:

```bash
python examples/compare_example.py      # PCG* vs WC-PCG* vs G-EDF
```

## Algorithms

`pcg_star` (DP-fair allocation), `wc_pcg_star` (WK allocation, remaining-time
order), `wc_pcg_star_idx` (WK allocation, index order), `g_edf`.

## Credits

The PCG\* local scheduler (`src/unifsim/schedulers/dp/local/`) is ported from the
reference PCG implementation by Antoine Bertout and Pascal Richard; the WK
allocation and the metric definitions follow shrimp. `tests/oracle` checks the
port against the reference (skipped unless the reference package `pcg` is
importable):

```bash
PYTHONPATH=/path/to/pcg-main/src:/path/to/pcg-main pytest tests/oracle
```
