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

# Minimum margin floor (percentage points) to prevent division by near-zero
_MIN_MARGIN_PP = 0.5

# Normalization constant: derived from PA (0.28) at 1pp margin = 100
# NORM = 100 / (0.28 * (1/1.0)) = 357.14
_NORM = 100.0 / 0.28

# Default score for counties with no margin data
_NULL_MARGIN_DEFAULT = 15.0


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
    raw = state_tipping_weight * (1.0 / abs_margin)
    return min(100.0, round(raw * _NORM, 2))
