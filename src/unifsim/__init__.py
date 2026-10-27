"""unifsim: exact simulator for real-time scheduling on uniform multiprocessors.

    from unifsim import Task, Platform, System, run, compare
    r = run(system, "pcg_star")      # simulate + validate + metrics
    r.report(); r.schedule()
    compare(system, ["pcg_star", "wc_pcg_star", "g_edf"], "report.html")
"""

__version__ = "0.1.0"

from .api import Result, run
from .gui import compare
from .model import Platform, System, Task

__all__ = ["Platform", "Result", "System", "Task", "compare", "run"]
