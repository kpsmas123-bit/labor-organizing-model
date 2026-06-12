"""
Terrain v2.0 — Sector Strategic Value Score (SVS)

Computes SVS for a sector from its component scores.
Formula: SVS = cap_reach + comm_reach + comm_facing + non_off
               + dual_crisis_bonus + whole_worker_bonus

Theoretical grounding:
- Capital Crisis Reach: Silver (2003), Womack (2005) — workplace bargaining power
- Community Crisis Reach: McAlevey (2016) — whole-worker organizing
- Community Facing Reach: McAlevey (2016) — worker-community boundary
- Non-Offshoreable: Silver (2003) — spatial fix resistance
- Dual Crisis Bonus: Fox-Hodess (2023) — compounding disruption effect
- Whole Worker Bonus: McAlevey (2016) — associational power activation

Config: config/weights.json → svs_formula
"""

import json
from pathlib import Path


def load_svs_weights() -> dict:
    """Load SVS formula parameters from config."""
    config_path = Path(__file__).parent.parent / "config" / "weights.json"
    with open(config_path) as f:
        return json.load(f)["svs_formula"]


def score_svs(
    cap_reach: int,
    comm_reach: int,
    comm_facing: int,
    non_off: int,
    weights: dict = None
) -> float:
    """
    Compute SVS for a single sector.

    Args:
        cap_reach: Capital Crisis-Creating Reach ordinal (0=none,1=local,2=state,3=national)
        comm_reach: Community Crisis-Creating Reach ordinal (0-3)
        comm_facing: Community-Facing Reach ordinal (0-3)
        non_off: Non-Offshoreable level ordinal (0=none,1=partial,2=full)
        weights: SVS formula weights from config. Loads from config if None.

    Returns:
        SVS score (float, 0-80)
    """
    if weights is None:
        weights = load_svs_weights()

    reach_pts = weights["reach_points"]
    facing_pts = weights["facing_points"]
    non_off_pts = weights["non_off_points"]

    reach_map = {"none": 0, "local": 1, "state": 2, "national": 3}
    facing_map = {"none": 0, "local": 1, "state": 2, "national": 3}
    non_off_map = {"none": 0, "partial": 1, "full": 2}

    rev_reach = {v: k for k, v in reach_map.items()}
    rev_facing = {v: k for k, v in facing_map.items()}
    rev_non_off = {v: k for k, v in non_off_map.items()}

    cap_key = rev_reach.get(cap_reach, "none")
    comm_key = rev_reach.get(comm_reach, "none")
    facing_key = rev_facing.get(comm_facing, "none")
    non_off_key = rev_non_off.get(non_off, "none")

    score = (
        reach_pts[cap_key]
        + reach_pts[comm_key]
        + facing_pts[facing_key]
        + non_off_pts[non_off_key]
    )

    if cap_reach > 0 and comm_reach > 0:
        score += weights["dual_crisis_bonus"]

    if comm_reach > 0 and comm_facing > 0:
        score += weights["whole_worker_bonus"]

    return float(score)
