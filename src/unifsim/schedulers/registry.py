"""Scheduler names used in campaign specifications -> constructors."""

from .dpfair.budgets import nominal
from .dpfair.pcg_star import PCGStar
from .global_.g_edf import GEDF

REGISTRY = {
    "g_edf": GEDF,
    "pcg_star": lambda: PCGStar(budget=nominal),
}


def make(name: str):
    try:
        return REGISTRY[name]()
    except KeyError:
        raise KeyError(f"unknown scheduler {name!r}; known: {sorted(REGISTRY)}") from None
