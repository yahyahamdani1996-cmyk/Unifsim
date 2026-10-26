"""Tasks and jobs. All quantities are exact (int or Fraction)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from numbers import Rational


def exact(x, name: str = "value") -> Fraction:
    """Convert x to Fraction, rejecting floats and bools.

    Accepted: int, Fraction, str parsable by Fraction ("7/2", "3").
    """
    if isinstance(x, bool):
        raise TypeError(f"{name}: bool is not a number")
    if isinstance(x, float):
        raise TypeError(f"{name}: float {x!r} rejected, use int, Fraction or str")
    if isinstance(x, (int, Rational)):
        return Fraction(x)
    if isinstance(x, str):
        return Fraction(x)
    raise TypeError(f"{name}: unsupported type {type(x).__name__}")


def exact_int(x, name: str = "value") -> int:
    f = exact(x, name)
    if f.denominator != 1:
        raise ValueError(f"{name}: must be an integer, got {f}")
    return int(f)


@dataclass(frozen=True)
class Task:
    """Periodic task tau = (C, T, D), synchronous release at 0.

    C is the work at speed 1, so C > D is valid on a uniform platform whose
    fastest processor has s_1 > 1 (u = C/T can exceed 1, up to s_1).
    D defaults to T (implicit deadline). Invariant: C > 0 and 0 < D <= T.
    """

    id: int
    C: Fraction
    T: int
    D: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "C", exact(self.C, f"task {self.id} C"))
        object.__setattr__(self, "T", exact_int(self.T, f"task {self.id} T"))
        d = self.T if self.D is None else exact_int(self.D, f"task {self.id} D")
        object.__setattr__(self, "D", d)
        if not (self.C > 0 and 0 < self.D <= self.T):
            raise ValueError(
                f"task {self.id}: requires C > 0 and 0 < D <= T, got C={self.C}, D={self.D}, T={self.T}"
            )

    @property
    def u(self) -> Fraction:
        return self.C / self.T

    @property
    def implicit(self) -> bool:
        return self.D == self.T


@dataclass(frozen=True, order=True)
class Job:
    """k-th job of a task (k >= 0). Identity = (task_id, k)."""

    task_id: int
    k: int
    release: Fraction
    deadline: Fraction
    C: Fraction

    @staticmethod
    def of(task: Task, k: int) -> "Job":
        r = Fraction(k * task.T)
        return Job(task.id, k, r, r + task.D, task.C)

    @property
    def name(self) -> str:
        return f"T{self.task_id}_{self.k}"

    def __str__(self) -> str:
        return self.name
