"""groups@1: task sets of the PCG*_S paper, Sec. 7.2.

  1. periods drawn uniformly from the integers in period_range (paper: [10, 100]);
  2. the n tasks are assigned at random to m non-empty processor groups;
  3. in the group of processor q, positive random weights, normalized so that the
     utilizations sum to y * s_q, with y = U / S_m (paper: y = 0.70);
  4. C_i = u_i * T_i; rejection unless Horvath-feasible.
Each group fits its processor, so the system is feasible (step 4 never rejects
in practice). Exact arithmetic: integer weights in [1, weight_max].
The platform is given (campaign: random_platform, whose slowest speed is 1).
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np

from ..model.system import System
from ..model.task import Task, exact
from .cfs_uniform import GenerationError


def groups(n, U, platform, seed, period_range=(10, 100), weight_max=1000, max_tries=1000, **_cfs_options):
    m = platform.m
    if n < m:
        raise GenerationError(f"groups: n={n} < m={m}, the {m} groups cannot all be non-empty")
    lo, hi = (int(x) for x in period_range)
    if not 1 <= lo <= hi:
        raise GenerationError(f"groups: period_range must satisfy 1 <= lo <= hi, got {lo}-{hi}")
    S = sum(platform.speeds, Fraction(0))
    y = exact(U, "U") / S
    if not 0 < y <= 1:
        raise GenerationError(f"groups: U / S_m = {y} must be in (0, 1]")
    rng = np.random.default_rng(seed)
    for _ in range(max_tries):
        T = [int(x) for x in rng.integers(lo, hi + 1, size=n)]
        while True:
            g = [int(x) for x in rng.integers(0, m, size=n)]
            if len(set(g)) == m:
                break
        w = [int(x) for x in rng.integers(1, weight_max + 1, size=n)]
        u = [Fraction(0)] * n
        for q in range(m):
            idx = [i for i in range(n) if g[i] == q]
            tot = sum(w[i] for i in idx)
            for i in idx:
                u[i] = y * platform.speeds[q] * Fraction(w[i], tot)
        system = System(tasks=tuple(Task(i, u[i] * T[i], T[i]) for i in range(n)), platform=platform,
                        meta={"generator": "groups@1", "y": str(y), "period_range": [lo, hi], "seed": seed})
        if system.horvath_feasible():
            return system
    raise GenerationError(f"groups: no feasible set in {max_tries} tries")
