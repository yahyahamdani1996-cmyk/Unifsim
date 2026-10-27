"""cfs_uniform@1: random implicit-deadline periodic task sets for a given uniform platform.

Method (from shrimp core/generate_task.py, tested in the WC-PCG* campaigns):
  1. utilization vector of n tasks summing to U, uniformly in
     [u_min, u_max]^n (ConvolutionalFixedSum, cfsa);
  2. quantization of each u_i to a multiple of `quantum`;
  3. rejection unless the system is feasible (Horvath conditions);
  4. period of each task drawn uniformly from `periods`, C_i = u_i * T_i.

Differences with the shrimp script, each one switchable to the old behaviour:
  - seeded: same parameters + seed  ->  same System (shrimp: unseeded);
  - rounding="exact_sum" (default): the quantized utilizations sum to U exactly
    (largest remainder). rounding="independent" rounds each u_i alone, as in
    shrimp: the sum then differs from U by up to n * quantum / 2;
  - order="random" (default): task ids in the order drawn by cfsa (exchangeable).
    order="sorted": task 0 = largest utilization, as in shrimp.
"""

from __future__ import annotations

from fractions import Fraction
from math import floor

import numpy as np

from ..model.platform import Platform
from ..model.system import System
from ..model.task import Task, exact
from .seeds import derive_seed

NAME = "cfs_uniform"
VERSION = 1


class GenerationError(Exception):
    pass


def _quantize_exact_sum(raw, U, q, u_min, u_max):
    """Multiples of q, each in [u_min, u_max], summing exactly to U (largest remainder)."""
    units_total = U / q
    if units_total.denominator != 1:
        raise GenerationError(f"U={U} is not a multiple of quantum={q}")
    scaled = [Fraction(float(u)) / q for u in raw]          # exact value of the float
    base = [floor(x) for x in scaled]
    missing = int(units_total) - sum(base)
    order = sorted(range(len(raw)), key=lambda i: scaled[i] - base[i], reverse=True)
    if not 0 <= missing <= len(raw):
        return None                                           # float error beyond one unit per task
    for i in order[:missing]:
        base[i] += 1
    out = [b * q for b in base]
    if any(u < u_min or u > u_max for u in out):
        return None
    return out


def _quantize_independent(raw, q):
    return [Fraction(round(float(u) / q)) * q for u in raw]


def cfs_uniform(n, U, platform, periods, u_min="1/100", u_max=None, quantum="1/10000",
                seed=1, rounding="exact_sum", order="random", max_attempts=1000) -> System:
    """One feasible task set. Deterministic in all its arguments.

    n, U        : number of tasks, total utilization (exact, multiple of quantum)
    platform    : Platform (or tuple of speeds)
    periods     : tuple of integer periods to draw from
    u_min, u_max: per-task utilization bounds; u_max defaults to the fastest speed
    """
    from convolutionalfixedsum import CFSAConfig, cfsa

    platform = platform if isinstance(platform, Platform) else Platform(tuple(platform))
    U, q, u_min = exact(U, "U"), exact(quantum, "quantum"), exact(u_min, "u_min")
    u_max = platform.speeds[0] if u_max is None else exact(u_max, "u_max")
    periods = tuple(int(p) for p in periods)
    if rounding not in ("exact_sum", "independent"):
        raise ValueError(f"rounding must be 'exact_sum' or 'independent', got {rounding!r}")
    if order not in ("random", "sorted"):
        raise ValueError(f"order must be 'random' or 'sorted', got {order!r}")
    if not (n * u_min <= U <= n * u_max):
        raise GenerationError(f"U={U} outside [n*u_min, n*u_max] = [{n * u_min}, {n * u_max}]")

    for attempt in range(max_attempts):
        s = derive_seed(NAME, VERSION, seed, attempt)
        try:
            raw = cfsa(n, total=float(U), lower_constraints=[float(u_min)] * n,
                       upper_constraints=[float(u_max)] * n, config=CFSAConfig(seed=s))
        except ZeroDivisionError:
            continue
        if rounding == "exact_sum":
            u = _quantize_exact_sum(raw, U, q, u_min, u_max)
            if u is None:
                continue
        else:
            u = _quantize_independent(raw, q)
        if order == "sorted":
            u = sorted(u, reverse=True)
        if any(x <= 0 for x in u):
            continue
        rng = np.random.default_rng(s)
        T = [int(periods[k]) for k in rng.integers(0, len(periods), size=n)]
        tasks = tuple(Task(i, u[i] * T[i], T[i]) for i in range(n))
        meta = {
            "generator": f"{NAME}@{VERSION}",
            "params": {"n": n, "U": str(U), "u_min": str(u_min), "u_max": str(u_max),
                       "quantum": str(q), "periods": list(periods),
                       "rounding": rounding, "order": order},
            "seed": seed,
            "attempts": attempt + 1,
            "U_reached": str(sum(u, Fraction(0))),
            "max_task_share": str(max(u) / sum(u)),
        }
        system = System(tasks, platform, meta)
        if system.horvath_feasible():
            return system
    raise GenerationError(f"no feasible task set after {max_attempts} attempts (n={n}, U={U}, seed={seed})")
