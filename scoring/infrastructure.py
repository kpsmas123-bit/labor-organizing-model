"""
Terrain v2.0 — Infrastructure Scoring Functions

Infrastructure scores measure existing union presence.
Used in Intervention Type classification (Phase 3).
NOT in OOS or primary scores.

Sources: DOL LM-2 union locals + BLS state density estimates.

Config: config/thresholds.json → organized_scale, union_culture
        config/weights.json → infrastructure_composite
"""

import json
from pathlib import Path


def _load_thresholds() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "thresholds.json"
    with open(config_path) as f:
        return json.load(f)


def _load_weights() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "weights.json"
    with open(config_path) as f:
        return json.load(f)


def score_organized_scale(
    total_members: int,
    union_count: int
) -> float:
    """
    Score existing union scale by member count.
    Phase 3 input — not in v2.0 primary scores.

    Config: config/thresholds.json → organized_scale
    """
    t = _load_thresholds()["organized_scale"]

    for bracket in t["brackets"]:
        if total_members >= bracket["min_members"]:
            return float(bracket["score"])

    return min(100.0, max(0.0, float(union_count * t["sub_floor_multiplier"])))


def score_union_culture(
    total_members: int,
    total_workforce: int
) -> float:
    """
    Score union culture by membership density.
    Phase 3 input — not in v2.0 primary scores.

    Config: config/thresholds.json → union_culture
    """
    if total_workforce == 0:
        return 5.0

    t = _load_thresholds()["union_culture"]
    density = total_members / total_workforce

    for bracket in t["brackets"]:
        if "min_density" in bracket and density >= bracket["min_density"]:
            return float(bracket["score"])

    return 5.0


def infrastructure_composite(
    organized_scale: float,
    union_culture: float
) -> float:
    """
    Combine organized scale and union culture into infrastructure score.
    Phase 3 input — used in Intervention Type classification.

    Config: config/weights.json → infrastructure_composite
    """
    w = _load_weights()["infrastructure_composite"]
    return round(
        organized_scale * w["organized_scale"]
        + union_culture * w["union_culture"],
        2
    )


def classify_intervention(
    infra: float,
    electoral: float,
    statewide: float
) -> str:
    """
    Classify county intervention type (A/B/C).
    Phase 3 output — categorical, not a score.

    Type A: Organize Unorganized (low infrastructure)
    Type B: Political Activation (infrastructure but low political alignment)
    Type C: Partnership (high infrastructure + high political activation)

    Config: config/thresholds.json → intervention_type
    """
    t = _load_thresholds()["intervention_type"]

    if infra < t["infra_type_a_ceiling"]:
        return "Type A: Organize Unorganized"
    elif infra >= t["infra_type_a_ceiling"] and electoral >= t["electoral_type_c_floor"]:
        if statewide < t["statewide_type_b_ceiling"]:
            return "Type B: Political Activation"
        else:
            return "Type C: Partnership"
    else:
        return "Type B: Political Activation"
