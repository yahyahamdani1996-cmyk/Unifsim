"""Stable seed derivation.

Seeds are derived with SHA-256 of the parameters, never with Python's hash()
(salted per process), so a seed is the same in every process, on every machine
and whatever the number of parallel workers.
"""

from __future__ import annotations

import hashlib


def derive_seed(*parts) -> int:
    """Deterministic seed in [1, 2**63 - 1] from any printable parameters.

    Never 0: convolutionalfixedsum treats seed=0 as "no seed"."""
    blob = "\x1f".join(str(p) for p in parts).encode()
    return int.from_bytes(hashlib.sha256(blob).digest()[:8], "big") % (2**63 - 1) + 1
