"""Scheduler interface. The scheduler only decides; the engine executes."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from types import MappingProxyType

from ..model.task import Job


@dataclass(frozen=True)
class Decision:
    """assignment: processor index -> job (absent processor = idle).
    wake_at: next instant (> t) at which the scheduler must be called again,
    in addition to releases, completions and deadlines."""

    assignment: dict[int, Job] = field(default_factory=dict)
    wake_at: Fraction | None = None


class View:
    """Read-only view of the engine state given to decide()."""

    def __init__(self, t, platform, active, remaining):
        self.t = t
        self.platform = platform
        self.active: tuple[Job, ...] = active
        self._remaining = MappingProxyType(remaining)

    def remaining(self, job: Job) -> Fraction:
        return self._remaining[job]


class Scheduler:
    name = "scheduler"

    def init(self, taskset, horizon) -> None:
        self.taskset = taskset
        self.platform = taskset.platform
        self.horizon = horizon

    def on_release(self, job: Job, t: Fraction) -> None:
        pass

    def on_completion(self, job: Job, t: Fraction) -> None:
        pass

    def decide(self, t: Fraction, view: View) -> Decision:
        raise NotImplementedError

    def trace_planes(self):
        """Deadline-partitioned (DP) schedulers return their PlaneRecords; others none."""
        return []
