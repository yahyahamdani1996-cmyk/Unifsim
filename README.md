# pcgsim

Exact, independently validated simulator for real-time scheduling on uniform
multiprocessor platforms (DP-fair and non DP-fair algorithms).

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

Step 1: model, engine, trace, validator, G-EDF.
