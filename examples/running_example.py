"""Running example of the paper (Tables 2 and 3).  Run:  python examples/running_example.py"""

from unifsim import Platform, System, Task, compare, run

system = System(
    tasks=(Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4),     # Task(id, C, T)
           Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
    platform=Platform((6, 3, 2, 2, 1)),                      # speeds, fastest first
)

r = run(system, "pcg_star")      # simulate + validate + metrics
r.schedule()                     # the schedule
r.report()                       # the metrics

compare(system, ["pcg_star", "wc_pcg_star", "g_edf"], "report.html")   # HTML report
