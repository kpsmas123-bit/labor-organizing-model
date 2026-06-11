"""
Terrain v2.0 — Electoral Scoring Functions

P1 Electoral Leverage (v2.0 target):
    p1 = state_tipping_weight × (1 / abs(county_margin))
    Simplified proxy for full two-stage Banzhaf (planned v3.0).
    Grounded in Banzhaf (1968), Feigenbaum et al. (2018).

Legacy electoral sub-scores (v1, kept for backward compatibility
during migration, superseded by P1 in v2.0):
    - score_presidential()
    - score_statewide()
    - score_congressional()
    - electoral_composite()

Config: config/thresholds.json → presidential_score, statewide_score,
        congressional_score
        config/weights.json → electoral_composite
"""

import json
from pathlib import Path
from typing import Optional


def _load_thresholds() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "thresholds.json"
    with open(config_path) as f:
        return json.load(f)


def _load_weights() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "weights.json"
    with open(config_path) as f:
        return json.load(f)


def score_p1_presidential(
    county_margin: Optional[float],
    state_tipping_weight: float
) -> float:
    """
    Compute P1 Electoral Leverage — Presidential (v2.0 formula).

    Args:
        county_margin: (D-R)/total × 100 for 2024 presidential election
        state_tipping_weight: probability this state is decisive (0-1)

    Returns:
        P1 score normalized to 0-100.
    """
    t = _load_thresholds()
    if county_margin is None:
        return float(t["presidential_score"]["null_margin_default"])
    abs_margin = max(abs(county_margin), 0.01)
    raw = state_tipping_weight * (1 / abs_margin)
    return min(100.0, round(raw * 100, 2))


def score_presidential(
    margin_2024: Optional[float],
    state_abbr: str
) -> int:
    """
    Legacy presidential score (v1 stepped formula).
    SUPERSEDED by score_p1_presidential() in v2.0.
    Kept for backward compatibility during migration.

    Config: config/thresholds.json → presidential_score, swing_states_presidential
    """
    t = _load_thresholds()
    swing_states = set(t["swing_states_presidential"]["states"])
    ps = t["presidential_score"]

    if margin_2024 is None:
        return ps["null_margin_default"]

    abs_margin = abs(margin_2024)

    if state_abbr in swing_states:
        a = ps["swing_state_part_a"]
    else:
        a = ps["non_swing_part_a"][-1]["score"]
        for bracket in ps["non_swing_part_a"][:-1]:
            if abs_margin <= bracket["max_margin"]:
                a = bracket["score"]
                break

    b = ps["part_b"][-1]["score"]
    for bracket in ps["part_b"][:-1]:
        if abs_margin <= bracket["max_margin"]:
            b = bracket["score"]
            break

    return min(100, a + b)


def score_statewide(
    state_margin: Optional[float],
    county_margin: Optional[float]
) -> int:
    """
    Legacy statewide score (v1 stepped formula).
    SUPERSEDED by P1 state legislative score in v2.0.

    Config: config/thresholds.json → statewide_score
    """
    t = _load_thresholds()["statewide_score"]

    margin = state_margin if state_margin is not None else county_margin
    if margin is None:
        return t["null_margin_default"]

    abs_margin = abs(margin)
    score = t["brackets"][-1]["score"]
    for bracket in t["brackets"][:-1]:
        if abs_margin <= bracket["max_margin"]:
            score = bracket["score"]
            break

    if margin >= t["safe_dem_threshold"]:
        score += t["safe_dem_bonus"]

    return min(100, score)


def score_congressional(
    margin_2024: Optional[float],
    trifecta: Optional[str]
) -> int:
    """
    Legacy congressional score (v1 — uses presidential margin as proxy).
    SUPERSEDED by P1 congressional score in v2.0 Phase 2B.

    Config: config/thresholds.json → congressional_score
    """
    t = _load_thresholds()["congressional_score"]

    if margin_2024 is None:
        return t["null_margin_default"]

    abs_margin = abs(margin_2024)
    score = t["brackets"][-1]["score"]
    for bracket in t["brackets"][:-1]:
        if abs_margin <= bracket["max_margin"]:
            score = bracket["score"]
            break

    if trifecta == "Divided":
        score += t["divided_trifecta_bonus"]

    return min(100, score)


def electoral_composite(
    presidential: float,
    statewide: float,
    congressional: float
) -> float:
    """
    Legacy electoral composite (v1).
    SUPERSEDED by P1 in v2.0.

    Config: config/weights.json → electoral_composite
    """
    w = _load_weights()["electoral_composite"]
    return round(
        presidential * w["presidential"]
        + statewide * w["statewide"]
        + congressional * w["congressional"],
        2
    )
