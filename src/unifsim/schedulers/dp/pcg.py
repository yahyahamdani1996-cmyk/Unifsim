"""PCG*, all the events of an instant handled together (ECRTS 2026, Algorithms 1 and 2)."""

from .base import DP
from .budgets import dp_fair
from  .local.pcg import pcg


class PCG(DP):
    name = "pcg"

    def __init__(self, budget=dp_fair):
        super().__init__(budget)

    def schedule_plane(self, budgets, speeds, length):
        return pcg(budgets, speeds, length)
