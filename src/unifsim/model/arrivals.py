"""Arrival models: how the jobs of a System are released.

The System holds the tasks and the platform; the arrival model turns them into
jobs. The same System can be simulated with different arrival models.

v1: Periodic only (synchronous, job k of task i released at k * T_i). Sporadic
models will implement the same method, with their own seed, and the TL-plane
boundaries of DP schedulers will then be computed as jobs arrive.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Periodic:
    name: str = "periodic"

    def jobs(self, system, horizon):
        """All jobs released strictly before horizon, sorted by (release, task id)."""
        return system.jobs(horizon)

    def to_dict(self) -> dict:
        return {"model": self.name}
