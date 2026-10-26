# unifsim

Exact, independently validated simulator for real-time scheduling on uniform
multiprocessor platforms (deadline-partitioned and global algorithms).

- Exact arithmetic: `int` and `Fraction` only, no epsilon, `float` rejected.
- The scheduler decides, the engine executes, the validator checks the trace
  without reusing engine code, the metrics are computed from the trace.

## Install

```bash
python -m venv venv && source venv/bin/activate
pip install -e ".[test]"
pytest
```

## Status

- Step 1: model, engine, trace, validator, G-EDF.
- Step 2: `DP` base class, dp_fair budget, PCG* (port of the reference
  implementation by A. Bertout and P. Richard, identical schedules on the
  oracle tests in `tests/oracle`).

## Oracle tests

`tests/oracle` compares PCG* with the reference implementation. It is skipped
unless the reference package `pcg` is importable:

```bash
PYTHONPATH=/path/to/pcg-main/src:/path/to/pcg-main pytest tests/oracle
```
