"""
!!! DEPRECATED — DEAD CODE. DO NOT USE AS THE RECIPE. !!!

The canonical SLS implementation lives in pipeline/build_v2_canonical.py
(calc_sls_capital / calc_sls_community), which is what actually produces
data/county_scores.json. This module is NOT imported by the real build.

This file is WRONG in two ways and is kept only for historical reference:
  1. NORMALIZATION_DENOMINATOR = 100_000 here, but the calibrated value is
     210_000 (config/weights.json svs_normalization.denominator).
  2. score_sls_community below uses raw Σ(reach×emp)/denom. The real formula
     is share-weighted: Σ(comm_reach × employment_share) × 4, capped 100.
Trust config/weights.json + build_v2_canonical.py, not this file.

--- original docstring follows ---

Terrain v2.0 — Strategic Labor Score (SLS) scoring functions.

SLS-Capital: measures how much leverage organized labor in a county has
over capital — weighted by sector's capital-reach score and employment.

SLS-Community: measures how much leverage organized labor has over
community crisis points — weighted by sector's community-reach score.

Formula (both):
    SLS = min(100, Σ(reach_score[sector] × employment[sector]) / 100_000)

Normalization denominator 100_000 is from weights.json: svs_normalization.denominator.
Update that value if the score distribution shifts after Phase 4 calibration.

Theoretical grounding: McAlevey (2016) — power analysis distinguishes
capital-facing leverage (contract/bargaining power) from community-facing
leverage (social crisis intervention). See METHODOLOGY_V2.md §3.2.

NOTE: Full calculation requires per-sector employment from Notion/CBP.
pipeline/build_v2_scores.py uses proxies from v1 sectoral_score pending
Phase 4 full pipeline build. These functions implement the target formula.
"""

from typing import Optional


NORMALIZATION_DENOMINATOR = 100_000


def score_sls_capital(
    cap_reach_by_sector: dict,
    employment_by_sector: dict,
) -> float:
    """
    SLS-Capital: employment-weighted capital-reach score.

    Args:
        cap_reach_by_sector: {sector_id: cap_reach_score (0-25)} from SVS config
        employment_by_sector: {sector_id: employed_workers} in this county

    Returns:
        float 0–100
    """
    total = 0.0
    for sector_id, cap_reach in cap_reach_by_sector.items():
        emp = employment_by_sector.get(sector_id, 0) or 0
        total += float(cap_reach) * float(emp)
    return min(100.0, round(total / NORMALIZATION_DENOMINATOR, 2))


def score_sls_community(
    comm_reach_by_sector: dict,
    employment_by_sector: dict,
) -> float:
    """
    SLS-Community: employment-weighted community-reach score.

    Args:
        comm_reach_by_sector: {sector_id: comm_reach_score (0-15)} from SVS config
        employment_by_sector: {sector_id: employed_workers} in this county

    Returns:
        float 0–100
    """
    total = 0.0
    for sector_id, comm_reach in comm_reach_by_sector.items():
        emp = employment_by_sector.get(sector_id, 0) or 0
        total += float(comm_reach) * float(emp)
    return min(100.0, round(total / NORMALIZATION_DENOMINATOR, 2))
