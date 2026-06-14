"""
Terrain v2.0 — Electoral leverage scoring functions.

P1 Presidential: continuous formula replacing the legacy stepped brackets.

Formula:
    P1 = min(100, tipping_weight × (1 / max(MIN_MARGIN, abs(margin))) × NORM)

Where:
    tipping_weight: probability this state is the decisive state (from
                    data/state_tipping_weights.json, derived from 538 2024 cycle)
    margin:         county presidential margin in percentage points
                    (positive = Dem win, negative = Rep win)
    MIN_MARGIN:     0.5 pp floor prevents division near zero
    NORM:           357.14 — normalizes so that PA (tipping=0.28) at 1pp margin = 100

Normalization derivation:
    NORM = 100 / (max_tipping_weight × (1 / min_margin))
         = 100 / (0.28 × (1 / 1.0))
         = 357.14

This preserves the relative ordering of the legacy formula while replacing
arbitrary brackets with a continuous inverse relationship that reflects
McAlevey's theory: a county's presidential leverage is the product of
(a) how likely its state is to be decisive and
(b) how efficiently additional votes could swing the state (inverse of margin).

Theoretical grounding: McAlevey (2016) — county-level power analysis;
Gelman & King (1994) — electoral responsiveness to turnout.
See METHODOLOGY_V2.md §4.1 for full derivation.

NULL MARGIN DEFAULT: 15.0 — conservative placeholder. Counties missing
margin data are almost always small rural counties with stable R+40+ margins,
so 15 slightly overestimates but does not dominate the score.
"""

from typing import Optional

# Swing states for presidential P1 legacy formula (v1.0)
SWING_STATES = {"AZ", "GA", "MI", "NV", "NC", "PA", "WI"}

# Minimum margin floor (percentage points) to prevent division by near-zero
_MIN_MARGIN_PP = 0.5

# Default score for counties with no margin data
_NULL_MARGIN_DEFAULT = 20.0


def score_presidential(margin: Optional[float], state_abbr: str) -> int:
    """
    v1.0 legacy presidential score using bracket logic and swing-state bonus.
    Kept for backward compatibility; v2.0 uses score_p1_presidential.
    """
    if margin is None:
        return 20
    abs_margin = abs(margin)
    a = 50 if state_abbr in SWING_STATES else (
        35 if abs_margin <= 5 else
        25 if abs_margin <= 10 else
        15 if abs_margin <= 15 else 5
    )
    b = (50 if abs_margin <= 5 else
         35 if abs_margin <= 10 else
         20 if abs_margin <= 15 else
         10 if abs_margin <= 20 else 5)
    return min(100, a + b)


def score_statewide(
    state_margin: Optional[float],
    county_margin: Optional[float],
) -> int:
    """v1.0 statewide legislative score using margin brackets + safe-state bonus."""
    margin = state_margin if state_margin is not None else county_margin
    if margin is None:
        return 20
    abs_margin = abs(margin)
    score = (100 if abs_margin <= 3 else
             80 if abs_margin <= 6 else
             60 if abs_margin <= 10 else
             40 if abs_margin <= 15 else
             20 if abs_margin <= 20 else 10)
    if margin >= 15:
        score += 20
    return min(100, score)


def score_congressional(
    margin: Optional[float],
    trifecta: Optional[str],
) -> int:
    """v1.0 congressional score using margin brackets + divided-trifecta bonus."""
    if margin is None:
        return 20
    abs_margin = abs(margin)
    score = (100 if abs_margin <= 3 else
             80 if abs_margin <= 7 else
             60 if abs_margin <= 12 else
             40 if abs_margin <= 18 else
             20 if abs_margin <= 25 else 10)
    if trifecta == "Divided":
        score += 15
    return min(100, score)


def electoral_composite(
    presidential: int,
    statewide: int,
    congressional: int,
) -> float:
    """v1.0 electoral composite: weighted average of three component scores."""
    return round((presidential * 0.4) + (statewide * 0.3) + (congressional * 0.3), 2)


def score_p1_presidential(
    county_margin: Optional[float],
    state_tipping_weight: float,
) -> float:
    """
    P1 Presidential leverage score (v2.0 continuous formula).

    Args:
        county_margin: 2024 presidential margin in percentage points.
                       Positive = Dem win, negative = Rep win. None if missing.
        state_tipping_weight: probability this state is decisive (0.0–1.0)

    Returns:
        float 0–100
    """
    if county_margin is None:
        return _NULL_MARGIN_DEFAULT

    abs_margin = max(_MIN_MARGIN_PP, abs(county_margin))
    raw = state_tipping_weight * (1.0 / abs_margin) * 100.0
    return min(100.0, round(raw, 2))


def classify_quadrant(
    sls_capital: float,
    sls_community: float,
    p1: float,
    p2: Optional[float],
    thresholds: dict,
) -> str:
    """
    Dual-lens county quadrant classification (v2.0).

    Tier 1 — Transform: high SLS + high P1 + hostile incumbent (low P2)
    Tier 2 — Activate: high SLS + high P1 + aligned incumbent (high P2)
    Tier 2 — Build: high SLS + low P1 (build electoral conditions)
    Tier 3 — Electoral: low SLS + high P1 (build organizing base)
    Tier 4 — Lower Priority: neither threshold met

    SLS sub-type: capital / community / capital_community

    Args:
        sls_capital: SLS-Capital score (0–100)
        sls_community: SLS-Community score (0–100)
        p1: P1 tipping-point leverage score (0–100 for national; 0–1 for state)
        p2: Incumbent alignment score (0–1), or None if unavailable
        thresholds: dict with sls_capital_high_boundary, sls_community_high_boundary,
                    p1_high_boundary (or state_p1_high_boundary), p2_hostile_threshold,
                    p2_aligned_threshold

    Returns:
        str quadrant label
    """
    capital_high = sls_capital >= thresholds["sls_capital_high_boundary"]
    community_high = sls_community >= thresholds["sls_community_high_boundary"]
    p1_threshold = thresholds.get("pts_high_low_boundary",
                                  thresholds.get("p1_high_boundary", 5.0))
    p1_high = p1 >= p1_threshold
    sls_high = capital_high or community_high

    if capital_high and community_high:
        sls_type = "capital_community"
    elif capital_high:
        sls_type = "capital"
    elif community_high:
        sls_type = "community"
    else:
        sls_type = None

    p2_hostile = (p2 is not None and
                  p2 < thresholds.get("p2_hostile_threshold", 0.4))
    p2_aligned = (p2 is not None and
                  p2 >= thresholds.get("p2_aligned_threshold", 0.6))

    if sls_high and p1_high and p2_hostile:
        return f"tier1_{sls_type}"
    elif sls_high and p1_high and p2_aligned:
        return f"tier2_activate_{sls_type}"
    elif sls_high and p1_high:
        return f"tier2_unknown_{sls_type}"
    elif sls_high and not p1_high:
        return f"tier2_build_{sls_type}"
    elif p1_high and not sls_high:
        return "tier3_electoral"
    else:
        return "tier4"
