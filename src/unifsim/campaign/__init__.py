"""Campaigns: many schedulers on many reproducible task sets (docs/CAMPAIGN_DESIGN.md).

    unifsim campaign campaigns/pcg_star_v1_v2.toml      # run or resume
    unifsim campaign report results/pcg_star_v1_v2/     # HTML report
"""

from .runner import columns, run_campaign
from .spec import Point, Spec, SpecError, load, parse

__all__ = ["Point", "Spec", "SpecError", "columns", "load", "parse", "run_campaign"]
