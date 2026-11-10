"""Arrival models: how the jobs of a System are released.

The System holds the tasks and the platform; the arrival model turns them into
jobs. The same System can be simulated with different arrival models.

Periodic: synchronous, job k of task i released at k * T_i.
Sporadic: gaps T_i * (1 + alpha * U), seeded; alpha = 0 is periodic.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction

from .task import Job, exact


@dataclass(frozen=True)
class Periodic:
    name: str = "periodic"

    def jobs(self, system, horizon):
        """All jobs released strictly before horizon, sorted by (release, task id)."""
        return system.jobs(horizon)

    def to_dict(self) -> dict:
        return {"model": self.name}


@dataclass(frozen=True)
class Sporadic:
    """Sporadic releases: a_{i,j+1} = a_{i,j} + T_i * (1 + alpha * U_{i,j}),
    U uniform on {0, 1/N, ..., 1} (N = resolution, exact arithmetic).

    alpha = 0 gives periodic releases; alpha = 1 gives gaps in [T_i, 2 T_i].
    The gap is always >= T_i (minimum inter-arrival time respected).
    first_release: "zero" (a_{i,0} = 0) or "random" (a_{i,0} = T_i * U, U in [0, 1)).
    Each task has its own generator seeded by (seed, task id), and the draws do
    not depend on alpha: for a fixed seed, the gaps of different alpha values are
    nested (same U), so runs with different alpha are paired.
    """

    alpha: Fraction = Fraction(0)
    seed: int = 0
    first_release: str = "zero"
    resolution: int = 1000
    name: str = "sporadic"

    def __post_init__(self):
        object.__setattr__(self, "alpha", exact(self.alpha, "alpha"))
        if self.alpha < 0:
            raise ValueError(f"alpha must be >= 0, got {self.alpha}")
        if self.first_release not in ("zero", "random"):
            raise ValueError(f"first_release must be 'zero' or 'random', got {self.first_release!r}")
        if not (isinstance(self.resolution, int) and self.resolution > 0):
            raise ValueError(f"resolution must be a positive int, got {self.resolution!r}")

    def jobs(self, system, horizon):
        """All jobs released strictly before horizon, sorted by (release, task id)."""
        N = self.resolution
        out = []
        for task in system.tasks:
            rng = random.Random(f"{self.seed}:{task.id}")
            if self.first_release == "zero":
                r = Fraction(0)
            else:
                r = task.T * Fraction(rng.randrange(N), N)
            k = 0
            while r < horizon:
                out.append(Job(task.id, k, r, r + task.D, task.C))
                r += task.T * (1 + self.alpha * Fraction(rng.randint(0, N), N))
                k += 1
        out.sort(key=lambda j: (j.release, j.task_id, j.k))
        return out

    def to_dict(self) -> dict:
        return {"model": self.name, "alpha": str(self.alpha), "seed": self.seed,
                "first_release": self.first_release, "resolution": self.resolution}
