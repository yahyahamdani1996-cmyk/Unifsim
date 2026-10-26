"""Uniform platform: processor p has speed s_p, s_1 >= ... >= s_m > 0."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .task import exact


@dataclass(frozen=True)
class Platform:
    speeds: tuple[Fraction, ...]

    def __post_init__(self):
        s = tuple(exact(v, "speed") for v in self.speeds)
        if not s:
            raise ValueError("platform: at least one processor")
        if any(v <= 0 for v in s):
            raise ValueError(f"platform: speeds must be > 0, got {s}")
        if any(a < b for a, b in zip(s, s[1:])):
            raise ValueError(
                f"platform: speeds must be sorted non-increasing (processor index = rank), got {s}"
            )
        object.__setattr__(self, "speeds", s)

    @property
    def m(self) -> int:
        return len(self.speeds)

    def S(self, k: int) -> Fraction:
        """Cumulated capacity of the k fastest processors, 0 <= k <= m."""
        if not 0 <= k <= self.m:
            raise ValueError(f"S({k}) with m={self.m}")
        return sum(self.speeds[:k], Fraction(0))
