"""Task set = tasks + platform, JSON format, canonical hash, feasibility."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from fractions import Fraction
from math import lcm
from pathlib import Path

from .platform import Platform
from .task import Job, Task

FORMAT_VERSION = 1


@dataclass(frozen=True)
class TaskSet:
    tasks: tuple[Task, ...]
    platform: Platform
    meta: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self):
        object.__setattr__(self, "tasks", tuple(self.tasks))
        ids = [t.id for t in self.tasks]
        if len(set(ids)) != len(ids):
            raise ValueError(f"taskset: duplicate task ids {ids}")
        if not self.tasks:
            raise ValueError("taskset: no task")

    @property
    def n(self) -> int:
        return len(self.tasks)

    @property
    def U(self) -> Fraction:
        return sum((t.u for t in self.tasks), Fraction(0))

    @property
    def hyperperiod(self) -> int:
        return lcm(*(t.T for t in self.tasks))

    def task(self, task_id: int) -> Task:
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    def jobs(self, horizon) -> list[Job]:
        """All jobs released strictly before horizon, sorted by (release, task id)."""
        out = []
        for t in self.tasks:
            k = 0
            while k * t.T < horizon:
                out.append(Job.of(t, k))
                k += 1
        out.sort(key=lambda j: (j.release, j.task_id, j.k))
        return out

    # ------------------------------------------------------------ feasibility
    def horvath_feasible(self) -> bool:
        """Exact feasibility for implicit-deadline periodic tasks on a uniform
        platform (Horvath et al.; Funk, Goossens, Baruah, RTSS 2001):
        sum of the k largest utilizations <= S_k for k < m, and U <= S_m."""
        if not all(t.implicit for t in self.tasks):
            raise NotImplementedError("exact test only for implicit deadlines")
        u = sorted((t.u for t in self.tasks), reverse=True)
        m = self.platform.m
        acc = Fraction(0)
        for k in range(1, min(m - 1, len(u)) + 1):
            acc += u[k - 1]
            if acc > self.platform.S(k):
                return False
        return self.U <= self.platform.S(m)

    # ------------------------------------------------------------ serialization
    def canonical(self) -> dict:
        """Canonical form (without meta): sorted keys, reduced fractions as strings."""
        return {
            "format_version": FORMAT_VERSION,
            "speeds": [str(s) for s in self.platform.speeds],
            "tasks": [
                {"id": t.id, "C": str(t.C), "T": t.T, "D": t.D}
                for t in sorted(self.tasks, key=lambda t: t.id)
            ],
        }

    @property
    def hash(self) -> str:
        blob = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    def to_json(self) -> str:
        d = self.canonical()
        if self.meta:
            d["meta"] = self.meta
        return json.dumps(d, indent=2, sort_keys=True)

    @staticmethod
    def from_dict(d: dict) -> "TaskSet":
        if d.get("format_version") != FORMAT_VERSION:
            raise ValueError(f"unsupported format_version {d.get('format_version')}")
        platform = Platform(tuple(d["speeds"]))
        tasks = tuple(
            Task(t["id"], t["C"], t["T"], t.get("D")) for t in d["tasks"]
        )
        return TaskSet(tasks, platform, d.get("meta", {}))

    @staticmethod
    def from_json(text: str) -> "TaskSet":
        return TaskSet.from_dict(json.loads(text))

    @staticmethod
    def load(path) -> "TaskSet":
        return TaskSet.from_json(Path(path).read_text())

    def save(self, path) -> None:
        Path(path).write_text(self.to_json())
