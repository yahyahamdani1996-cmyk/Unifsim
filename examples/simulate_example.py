"""Minimal example: define a system, simulate an algorithm, check and print the result.

Run from the repository root:  python examples/simulate_example.py
"""

from unifsim.engine import DeadlineMiss, simulate
from unifsim.model import Platform, System, Task
from unifsim.schedulers.registry import make
from unifsim.validate import validate

# 1. The system: tasks (id, C, T) and processor speeds, fastest first, slowest = 1.
#    C is the work at speed 1. Use int, Fraction or "7/2", never floats.
system = System(
    tasks=(
        Task(0, 3, 2),      # u = 3/2
        Task(1, 2, 3),      # u = 2/3
        Task(2, 5, 6),      # u = 5/6
    ),
    platform=Platform((2, 1)),
)
print("U =", system.U, "| feasible (Horvath):", system.horvath_feasible(),
      "| hyperperiod =", system.hyperperiod)

# 2. Simulate an algorithm by its name ("pcg_star", "g_edf", ...).
for name in ("pcg_star", "g_edf"):
    print(f"\n=== {name} ===")
    try:
        trace = simulate(system, make(name))      # horizon = hyperperiod by default
    except DeadlineMiss as e:
        print("deadline miss:", e)
        continue

    # 3. Independent check of the whole schedule (raises ValidationError if wrong).
    validate(system, trace)
    print("schedule valid")

    # 4. The result: one line per execution segment.
    for s in sorted(trace.segments, key=lambda s: (s.start, s.proc)):
        print(f"  P{s.proc}  {s.job.name:6}  [{s.start}, {s.end})")

    # TL-planes and budgets (deadline-partitioned algorithms only).
    for p in trace.planes:
        budgets = ", ".join(f"{j.name}={b}" for j, b in p.budgets)
        print(f"  plane [{p.t0}, {p.t1}): {budgets}")
