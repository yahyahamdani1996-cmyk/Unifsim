"""PCG* = DPFair + the PCG* local scheduler (ECRTS 2026)."""

from .base import DPFair
from .budgets import nominal
from .local.pcg_star import pcg_star


class PCGStar(DPFair):
    name = "pcg_star"

    def __init__(self, budget=nominal):
        super().__init__(budget)

    def schedule_plane(self, budgets, speeds, length):
        return pcg_star(budgets, speeds, length)
