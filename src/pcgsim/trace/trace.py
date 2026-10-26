"""Trace: the only output of the engine, the only input of validator and metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from ..model.task import Job


@dataclass(frozen=True)
class Segment:
    proc: int
    job: Job
    start: Fraction
    end: Fraction


@dataclass(frozen=True)
class PlaneRecord:
    """A TL-plane [t0, t1) and the budget given to each job (DP-fair only)."""

    t0: Fraction
    t1: Fraction
    budgets: tuple[tuple[Job, Fraction], ...]


@dataclass
class Trace:
    m: int
    horizon: Fraction
    segments: list[Segment] = field(default_factory=list)
    planes: list[PlaneRecord] = field(default_factory=list)
    decisions: list[Fraction] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self._last_idx: list[int | None] = [None] * self.m

    def add(self, proc: int, job: Job, start: Fraction, end: Fraction) -> None:
        """Append [start, end) of job on proc, merging with the previous segment
        of that processor when it is the same job and contiguous."""
        i = self._last_idx[proc]
        if i is not None:
            last = self.segments[i]
            if last.job == job and last.end == start:
                self.segments[i] = Segment(proc, job, last.start, end)
                return
        self.segments.append(Segment(proc, job, start, end))
        self._last_idx[proc] = len(self.segments) - 1

    def by_proc(self) -> list[list[Segment]]:
        out: list[list[Segment]] = [[] for _ in range(self.m)]
        for s in self.segments:
            out[s.proc].append(s)
        for lst in out:
            lst.sort(key=lambda s: s.start)
        return out
