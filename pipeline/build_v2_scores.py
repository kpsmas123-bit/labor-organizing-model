"""
Terrain v2.0 — First Scoring Run

Computes v2.0 scores for all counties using:
- Existing county_scores.json as data source (v1 data, read-only)
- scoring/sls.py for SLS-Capital and SLS-Community
- scoring/electoral.py for P1 Presidential

Output: data/county_scores_v2_test.json
NEVER overwrites data/county_scores.json.

Run modes:
  python pipeline/build_v2_scores.py --test    # 50 counties only
  python pipeline/build_v2_scores.py --full    # all 3,144 (requires approval)

Usage:
  python pipeline/build_v2_scores.py --test
"""

import json
import argparse
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scoring.sls import score_sls_capital, score_sls_community
from scoring.electoral import score_p1_presidential


def load_json(path: str):
    with open(path) as f:
        return json.load(f)


def load_state_tipping_weights():
    data = load_json("data/state_tipping_weights.json")
    default = data.get("_default", 0.005)
    return {k: v for k, v in data.items() if not k.startswith("_")}, default


def build_sector_reach_maps(county: dict) -> tuple[dict, dict]:
    """
    Extract cap_reach and comm_reach scores per sector
    from the county's existing sectoral data.

    In v1, county_scores.json stores sectoral_score (aggregate SVS × emp sum).
    For v2.0 SLS we need per-sector cap_reach and comm_reach scores.

    Since county_scores.json does not store per-sector breakdowns,
    we use the sectoral_score as a proxy for this first run:
    - sls_capital approximated from sectoral_score (v1 formula basis)
    - sls_community approximated from organizing_score (proxy)

    NOTE: This is a first-pass approximation. Full v2.0 requires
    reading per-sector employment and reach scores from Notion directly.
    Flagged in STATUS_V2.md for Phase 4 full pipeline build.
    """
    # Return empty dicts — we use proxy calculation below
    return {}, {}


def score_county_v2(county: dict, tipping_weights: dict,
                    default_weight: float) -> dict:
    """
    Compute v2.0 scores for one county.
    Returns a new dict with v2.0 fields added.
    """
    fips = county.get("fips", "")
    state = county.get("state", "")
    margin = county.get("margin_2024")

    # State tipping weight
    tipping_weight = tipping_weights.get(state, default_weight)

    # P1 Presidential (v2.0 formula)
    p1_presidential = score_p1_presidential(
        county_margin=margin,
        state_tipping_weight=tipping_weight
    )

    # SLS approximations from existing v1 scores
    # Full calculation requires per-sector Notion data (Phase 4)
    # Using sectoral_score as proxy for SLS-Capital (both measure
    # employment-weighted sector value; cap_reach is a component of SVS)
    sectoral = county.get("sectoral_score", 0) or 0
    organizing = county.get("organizing_score", 0) or 0

    # SLS-Capital proxy: sectoral_score already weights employment
    # by SVS which includes cap_reach. Scaling to same 0-100 range.
    sls_capital_proxy = min(100.0, round(float(sectoral), 2))

    # SLS-Community proxy: community crisis reach is captured by
    # the community lens in v1 (union_culture_score component).
    # Using a blend of sectoral and union_culture as proxy.
    union_culture = county.get("union_culture_score", 0) or 0
    sls_community_proxy = min(100.0, round(
        (float(sectoral) * 0.7 + float(union_culture) * 0.3), 2
    ))

    return {
        # Identity fields (copied from v1)
        "fips": fips,
        "county_name": county.get("county_name", ""),
        "state": state,
        "region": county.get("region", ""),
        "population": county.get("population"),
        "swing_state": county.get("swing_state", False),
        "margin_2024": margin,

        # v2.0 scores
        "sls_capital": sls_capital_proxy,
        "sls_community": sls_community_proxy,
        "p1_presidential": p1_presidential,
        "state_tipping_weight": tipping_weight,

        # Quadrant classification
        "sls_high": sls_capital_proxy >= 50,
        "p1_high": p1_presidential >= 50,
        "quadrant": classify_quadrant(sls_capital_proxy, p1_presidential),

        # Carry forward v1 scores for comparison during transition
        "v1_organizing_opportunity_score": county.get(
            "organizing_opportunity_score"),
        "v1_sectoral_score": sectoral,
        "v1_intervention_type": county.get("intervention_type"),
        "v1_priority_tier": county.get("priority_tier"),

        # Metadata
        "_model_version": "2.0-proxy",
        "_note": "SLS scores are proxies pending full per-sector Notion pipeline (Phase 4)",
        "_generated": datetime.now().isoformat()
    }


def classify_quadrant(sls: float, p1: float) -> str:
    """Classify county into one of four strategic quadrants."""
    sls_high = sls >= 50
    p1_high = p1 >= 50

    if sls_high and p1_high:
        return "1_deploy_now"
    elif sls_high and not p1_high:
        return "2_primary_target"
    elif not sls_high and p1_high:
        return "3_power_building"
    else:
        return "4_lower_priority"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true",
                        help="Run on 50 counties only")
    parser.add_argument("--full", action="store_true",
                        help="Run on all 3,144 counties")
    args = parser.parse_args()

    if not args.test and not args.full:
        print("ERROR: specify --test or --full")
        print("Always run --test first and review output before --full")
        return

    # Load data
    print("Loading county_scores.json...")
    counties = load_json("data/county_scores.json")
    print(f"Loaded {len(counties)} counties")

    print("Loading state tipping weights...")
    tipping_weights, default_weight = load_state_tipping_weights()

    # Subset for test run
    if args.test:
        # Pick 50 diverse counties: mix of states, sizes, swing/safe
        test_fips = {
            # Pennsylvania swing counties
            "42101", "42003", "42011", "42045", "42133",
            # Michigan
            "26163", "26081", "26099",
            # Wisconsin
            "55079", "55025", "55105",
            # Arizona
            "04013", "04019", "04021",
            # Georgia
            "13121", "13067", "13153",
            # Safe blue
            "06037", "06073", "36061",
            # Safe red
            "48201", "48113", "01073",
            # Rural swing
            "55001", "42027", "26001",
            # Small rural
            "56027", "48269", "38089",
            # Mixed
            "17031", "53033", "36005",
            "04001", "12086", "37183",
            "08031", "29510", "40109",
            "47157", "39049", "20091",
            "16001", "30049", "46099",
            "02020", "15003", "66010",
        }
        counties_to_score = [
            c for c in counties
            if str(c.get("fips", "")).zfill(5) in test_fips
        ]
        print(f"Test run: scoring {len(counties_to_score)} counties")
        output_path = "data/county_scores_v2_test.json"
    else:
        counties_to_score = counties
        output_path = "data/county_scores_v2_test.json"
        print(f"Full run: scoring all {len(counties_to_score)} counties")

    # Score counties
    results = []
    errors = []

    for i, county in enumerate(counties_to_score):
        try:
            scored = score_county_v2(county, tipping_weights, default_weight)
            results.append(scored)
        except Exception as e:
            errors.append({
                "fips": county.get("fips"),
                "county": county.get("county_name"),
                "error": str(e)
            })

    # Write output
    output = {
        "_generated": datetime.now().isoformat(),
        "_model_version": "2.0-proxy",
        "_source": "county_scores.json (v1 data)",
        "_counties_scored": len(results),
        "_errors": len(errors),
        "_note": (
            "SLS-Capital and SLS-Community are proxies in this run. "
            "Full per-sector calculation requires Phase 4 Notion pipeline. "
            "P1 Presidential uses v2.0 continuous formula."
        ),
        "counties": results,
        "errors": errors
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nOutput written to {output_path}")
    print(f"Counties scored: {len(results)}")
    print(f"Errors: {len(errors)}")

    # Print spot check — first 5 results
    print("\n--- SPOT CHECK: First 5 counties ---")
    for r in results[:5]:
        print(f"{r['county_name']}, {r['state']} (FIPS {r['fips']})")
        print(f"  SLS-Capital:   {r['sls_capital']}")
        print(f"  SLS-Community: {r['sls_community']}")
        print(f"  P1 Presidential: {r['p1_presidential']}")
        print(f"  State tipping weight: {r['state_tipping_weight']}")
        print(f"  Quadrant: {r['quadrant']}")
        print(f"  v1 OOS: {r['v1_organizing_opportunity_score']}")
        print()


if __name__ == "__main__":
    main()
