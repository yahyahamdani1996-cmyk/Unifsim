"""One-call usage: run() simulates, validates and measures; compare() writes the HTML report."""

from __future__ import annotations

from dataclasses import dataclass

from .engine import simulate
from .metrics import Metrics, compute_metrics
from .schedulers.registry import make
from .trace import Trace
from .validate import validate


@dataclass
class Result:
    system: object
    algorithm: str
    trace: Trace
    metrics: Metrics

    def schedule(self) -> None:
        for s in sorted(self.trace.segments, key=lambda s: (s.start, s.proc)):
            print(f"P{s.proc}  {s.job.name:7} [{s.start}, {s.end})")

    def report(self) -> None:
        print(self.metrics.report())


def run(system, algorithm, horizon=None) -> Result:
    """algorithm: a registry name ("pcg_star", "wc_pcg_star", "g_edf", ...) or a Scheduler object.
    Raises on a deadline miss, an invalid decision or an invalid schedule."""
    scheduler = make(algorithm) if isinstance(algorithm, str) else algorithm
    trace = simulate(system, scheduler, horizon)
    validate(system, trace)
    name = algorithm if isinstance(algorithm, str) else getattr(scheduler, "name", type(scheduler).__name__)
    return Result(system, name, trace, compute_metrics(system, trace))
