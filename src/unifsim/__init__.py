"""unifsim: exact simulator for real-time scheduling on uniform multiprocessors.

    from unifsim import Task, Platform, System, run, compare
    r = run(system, "pcg_star")      # simulate + validate + metrics
    r.report(); r.schedule()
    compare(system, ["pcg_star", "wc_pcg_star", "g_edf"], "report.html")

run, compare and Result are imported on first use, so that commands which do
not need the schedulers (unifsim gen) keep working while a scheduler in the
registry is being written.
"""

__version__ = "0.1.0"

from .model import Platform, System, Task

__all__ = ["Platform", "Result", "System", "Task", "compare", "run"]


def __getattr__(name):
    if name in ("run", "Result"):
        from . import api
        return getattr(api, name)
    if name == "compare":
        from .gui import compare
        return compare
    raise AttributeError(f"module 'unifsim' has no attribute {name!r}")
