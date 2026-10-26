"""PCG* = DP + the PCG* local scheduler (ECRTS 2026)."""

from .base import DP
from .budgets import dp_fair
from .local.pcg_star import pcg_star


class PCGStar(DP):
    name = "pcg_star"

    def __init__(self, budget=dp_fair):
        super().__init__(budget)

    def schedule_plane(self, budgets, speeds, length):
        return pcg_star(budgets, speeds, length)
