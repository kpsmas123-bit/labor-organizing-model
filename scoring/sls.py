"""
Terrain v2.0 — Strategic Leverage Score (SLS)

Two independent county-level scores:

SLS-Capital: absolute crisis-creating potential against capital
    = Σ(cap_reach_score × raw_employment_in_sector) / benchmark
    Raw employment count drives this. Scale matters for capital disruption.
    Grounded in Womack (2005) technically strategic positions.

SLS-Community: relational crisis-creating potential in community
    = Σ(comm_reach_score × employment_share_of_county_workforce)
    Share of workforce drives this. Structural centrality to community life.
    Grounded in McAlevey (2016) whole-worker model.

Config: config/weights.json → svs_normalization
"""

import json
from pathlib import Path
from typing import Dict


def load_normalization() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "weights.json"
    with open(config_path) as f:
        return json.load(f)["svs_normalization"]


def score_sls_capital(
    sector_employment: Dict[str, int],
    sector_cap_reach: Dict[str, float],
    benchmark: float = None
) -> float:
    """
    Compute SLS-Capital for a county.

    Args:
        sector_employment: {sector_id: raw_employment_count}
        sector_cap_reach: {sector_id: cap_reach_score (0/10/15/25)}
        benchmark: normalization denominator. Loads from config if None.

    Returns:
        SLS-Capital score normalized to 0-100.
    """
    if benchmark is None:
        benchmark = load_normalization()["denominator"]

    total = sum(
        sector_cap_reach.get(sid, 0) * emp
        for sid, emp in sector_employment.items()
    )
    return min(100.0, round(total / benchmark, 2))


def score_sls_community(
    sector_employment: Dict[str, int],
    sector_comm_reach: Dict[str, float],
    total_county_employment: int
) -> float:
    """
    Compute SLS-Community for a county.

    Args:
        sector_employment: {sector_id: raw_employment_count}
        sector_comm_reach: {sector_id: comm_reach_score (0/10/15/25)}
        total_county_employment: total workers across all sectors in county

    Returns:
        SLS-Community score normalized to 0-100.
    """
    if total_county_employment == 0:
        return 0.0

    total = sum(
        sector_comm_reach.get(sid, 0) * (emp / total_county_employment)
        for sid, emp in sector_employment.items()
    )
    return min(100.0, round(total * 100, 2))
