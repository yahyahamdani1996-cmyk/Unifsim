"""Random uniform platforms.

random_platform(m, lo, hi, seed): m integer speeds drawn uniformly in [lo, hi],
the smallest forced to 1, sorted fastest first (method of the ECRTS 2027
generator: "tirées aléatoirement entre 1 et 10, la plus petite forcée à 1,
puis triées").
"""

from __future__ import annotations

import numpy as np

from ..model.platform import Platform


def random_platform(m: int, lo: int = 1, hi: int = 10, seed: int = 1) -> Platform:
    if m < 1:
        raise ValueError("m must be >= 1")
    if not 1 <= lo <= hi:
        raise ValueError(f"speed range must satisfy 1 <= lo <= hi, got {lo}-{hi}")
    rng = np.random.default_rng(seed)
    s = sorted((int(x) for x in rng.integers(lo, hi + 1, size=m)), reverse=True)
    s[-1] = 1                                      # slowest processor always has speed 1
    return Platform(tuple(sorted(s, reverse=True)))
