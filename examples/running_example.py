"""Running example of the paper (Tables 2 and 3), scheduled by PCG*.

Run from the repository root:  python examples/running_example.py
"""

from unifsim.engine import simulate
from unifsim.metrics import compute_metrics
from unifsim.model import Platform, System, Task
from unifsim.schedulers.registry import make
from unifsim.validate import validate

system = System(
    tasks=(Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4),     # Task(id, C, T)
           Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
    platform=Platform((6, 3, 2, 2, 1)),                      # speeds, fastest first
)

trace = simulate(system, make("pcg_star"))   # 1. run
validate(system, trace)                       # 2. check
for s in trace.segments:                      # 3. read the schedule
    print(s.proc, s.job.name, s.start, s.end)

print(compute_metrics(system, trace).report())   # 4. metrics
