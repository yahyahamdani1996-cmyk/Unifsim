"""Running example of the paper (Tables 2 and 3): 6 tasks on 5 uniform processors.

Run from the repository root:  python examples/running_example.py
"""

from unifsim.engine import simulate
from unifsim.model import Platform, System, Task
from unifsim.schedulers.registry import make
from unifsim.validate import validate

# Table 2: task set tau (C_i, T_i), implicit deadlines. Ids 1..6 = tau_1..tau_6.
# Table 3: platform Pi, speeds s_j.
system = System(
    tasks=(
        Task(1, 33, 8),   # u = 4.125
        Task(2, 5, 2),    # u = 2.500
        Task(3, 7, 4),    # u = 1.750
        Task(4, 9, 8),    # u = 1.125
        Task(5, 4, 8),    # u = 0.500
        Task(6, 3, 8),    # u = 0.375
    ),
    platform=Platform((6, 3, 2, 2, 1)),
)

# Feasibility, as in (2): max over k of (sum of the k largest u) / S_k, with S_m for the total
u = sorted((t.u for t in system.tasks), reverse=True)
m, S = system.platform.m, system.platform.S
ratios = [sum(u[:k]) / S(k) for k in range(1, m)] + [system.U / S(m)]
print("ratios:", ", ".join(f"{float(r):.3f}" for r in ratios), "-> max =", f"{float(max(ratios)):.3f}")
print("feasible (Horvath):", system.horvath_feasible(), "| U =", system.U, "| H =", system.hyperperiod)

trace = simulate(system, make("pcg_star"))
validate(system, trace)
print("\nPCG*: schedule valid")

for p in trace.planes:
    print(f"\nTL-plane [{p.t0}, {p.t1})  budgets: " + ", ".join(f"{j.name}={b}" for j, b in p.budgets))
    for s in sorted(trace.segments, key=lambda s: (s.proc, s.start)):
        if p.t0 <= s.start < p.t1:
            print(f"  P{s.proc + 1} (s={system.platform.speeds[s.proc]})  {s.job.name:6}  [{s.start}, {s.end})")
