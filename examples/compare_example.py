"""Compare several algorithms on the paper's running example and open the report.

Run from the repository root:  python examples/compare_example.py
"""

import webbrowser

from unifsim.gui import compare
from unifsim.model import Platform, System, Task

system = System(
    tasks=(Task(1, 33, 8), Task(2, 5, 2), Task(3, 7, 4),     # Task(id, C, T)
           Task(4, 9, 8), Task(5, 4, 8), Task(6, 3, 8)),
    platform=Platform((6, 3, 2, 2, 1)),                      # speeds, fastest first
)

path = compare(system, ["pcg_star", "wc_pcg_star", "g_edf"], "report.html",
               title="Running example: PCG* vs WC-PCG* vs G-EDF")
print("report written to", path.resolve())
webbrowser.open(path.resolve().as_uri())
