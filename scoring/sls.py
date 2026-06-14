"""
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
    employment_by_sector: dict,
    comm_reach_by_sector: dict,
    total_employment: Optional[int] = None,
) -> float:
    """
    SLS-Community: share-weighted community-reach score.

    Community leverage is measured as the sector's share of the local workforce
    times its community-reach score. This captures local crisis leverage rather
    than absolute scale (which is captured by SLS-Capital).

    Args:
        employment_by_sector: {sector_id: employed_workers} in this county
        comm_reach_by_sector: {sector_id: comm_reach_score (0-25)} from SVS config
        total_employment: total county workforce. Falls back to NORMALIZATION_DENOMINATOR.

    Returns:
        float 0–100
    """
    if total_employment is not None:
        if total_employment == 0:
            return 0.0
        denom = float(total_employment)
    else:
        denom = float(NORMALIZATION_DENOMINATOR)
    total = 0.0
    for sector_id, emp in employment_by_sector.items():
        comm_reach = comm_reach_by_sector.get(sector_id, 0) or 0
        total += float(comm_reach) * (float(emp) / denom) * 100.0
    return min(100.0, round(total, 2))
