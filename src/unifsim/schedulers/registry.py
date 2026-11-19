"""Scheduler names used in campaign specifications -> constructors."""

from .dp.budgets import dp_fair, greedy_paper, greedy_wk
from .dp.pcg_star import PCGStar
from .dp.pcg_star_online import PCGStarOnline
from .dp.pcg_star_v2 import PCGStarV2
from .global_.g_edf import GEDF
from .dp.pcg import PCG

def _named(scheduler, name):
    scheduler.name = name
    return scheduler


def _dynamic(scheduler, name):
    scheduler.split = "dynamic"
    return _named(scheduler, name)


REGISTRY = {
    "g_edf": GEDF,
    "pcg_star": lambda: PCGStar(budget=dp_fair),
    "wc_pcg_star": lambda: _named(PCGStar(budget=greedy_wk("remaining")), "wc_pcg_star"),
    "wc_pcg_star_idx": lambda: _named(PCGStar(budget=greedy_wk("index")), "wc_pcg_star_idx"),
    "wc_pcg_star_paper": lambda: _named(PCGStar(budget=greedy_paper("remaining")), "wc_pcg_star_paper"),
    "pcg_star_online": lambda: PCGStarOnline(budget=dp_fair),
    "wc_pcg_star_online": lambda: _named(PCGStarOnline(budget=greedy_wk("remaining")), "wc_pcg_star_online"),
    "pcg_star_v2": lambda: PCGStarV2(budget=dp_fair),
    "wc_pcg_star_v2": lambda: _named(PCGStarV2(budget=greedy_wk("remaining")), "wc_pcg_star_v2"),
    "wc_pcg_star_v2_paper": lambda: _named(PCGStarV2(budget=greedy_paper("remaining")), "wc_pcg_star_v2_paper"),
    "pcg": lambda: PCG(budget=dp_fair),
    # dynamic TL-plane construction (sporadic releases); the names above are static
    "pcg_star_dyn": lambda: _dynamic(PCGStar(budget=dp_fair), "pcg_star_dyn"),
    "pcg_star_v2_dyn": lambda: _dynamic(PCGStarV2(budget=dp_fair), "pcg_star_v2_dyn"),
    "pcg_dyn": lambda: _dynamic(PCG(budget=dp_fair), "pcg_dyn"),
}


def make(name: str):
    try:
        return REGISTRY[name]()
    except KeyError:
        raise KeyError(f"unknown scheduler {name!r}; known: {sorted(REGISTRY)}") from None
