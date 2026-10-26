"""Scheduler names used in campaign specifications -> constructors."""

from .global_.g_edf import GEDF

REGISTRY = {
    "g_edf": GEDF,
}


def make(name: str):
    try:
        return REGISTRY[name]()
    except KeyError:
        raise KeyError(f"unknown scheduler {name!r}; known: {sorted(REGISTRY)}") from None
