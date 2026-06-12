"""
Terrain v2.0 — True Scoring Run (no proxies)

Uses real per-sector employment data from Agent A export
and real key vote scores from Agent C export.

Output: data/county_scores_v2_test.json

NEVER overwrites data/county_scores.json.

Run:
  python pipeline/build_v2_scores_true.py --test  (50 counties)
  python pipeline/build_v2_scores_true.py --full  (all 3,143)
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent


def load_json(rel_path):
    with open(ROOT / rel_path) as f:
        return json.load(f)


def load_csv(rel_path):
    with open(ROOT / rel_path) as f:
        return list(csv.DictReader(f))


def build_sector_points(sectors, weights):
    """Map sector_id → (cap_reach_points, comm_reach_points)."""
    reach_map = weights["svs_formula"]["reach_points"]
    ordinal_to_label = {0: "none", 1: "local", 2: "state", 3: "national"}
    result = {}
    for sid, s in sectors.items():
        cap_label = ordinal_to_label.get(s["cap_reach"], "none")
        comm_label = ordinal_to_label.get(s["comm_reach"], "none")
        result[sid] = {
            "cap": reach_map[cap_label],
            "comm": reach_map[comm_label],
        }
    return result


def calc_sls_capital(fips, county_sectors, sector_points, denominator):
    raw = sum(
        sector_points[sid]["cap"] * emp["total_employment"]
        for sid, emp in county_sectors.items()
        if sid in sector_points
    )
    return round(min(100.0, raw / denominator), 2)


def calc_sls_community(fips, county_sectors, sector_points):
    total_emp = sum(e["total_employment"] for e in county_sectors.values())
    if total_emp == 0:
        return 0.0
    weighted = sum(
        sector_points[sid]["comm"] * (emp["total_employment"] / total_emp)
        for sid, emp in county_sectors.items()
        if sid in sector_points
    )
    return round(min(100.0, weighted * 4), 2)


def build_crosswalk_index(crosswalk_rows):
    """county_fips → list of {district_state, district_number, overlap_weight}"""
    index = defaultdict(list)
    for row in crosswalk_rows:
        index[row["county_fips"]].append({
            "district_state": row["district_state"],
            "district_number": row["district_number"],
            "overlap_weight": float(row["overlap_weight"]),
        })
    return dict(index)


def build_p2_state_index(key_vote_rows):
    """state → list of {key_vote_score, chamber, member_name}"""
    index = defaultdict(list)
    for row in key_vote_rows:
        score_str = row.get("key_vote_score", "")
        if not score_str:
            continue
        index[row["state"]].append({
            "key_vote_score": float(score_str),
            "chamber": row["chamber"],
            "member_name": row["member_name"],
        })
    return dict(index)


def score_p1_presidential_formula(county_margin, state_tipping_weight):
    """Continuous formula from scoring/electoral.py."""
    if county_margin is None:
        return 15.0
    _MIN_MARGIN_PP = 0.5
    _NORM = 100.0 / 0.28
    abs_margin = max(_MIN_MARGIN_PP, abs(county_margin))
    raw = state_tipping_weight * (1.0 / abs_margin)
    return round(min(100.0, raw * _NORM), 2)


def calc_p1_congressional(fips, county_margin, state_tipping_weight,
                           crosswalk_index, tipping_weights):
    """
    P1 Congressional: district-crosswalk-weighted average of P1 scores.
    Uses county presidential margin as proxy for district margin (documented
    limitation — Phase 4B will add district-level margins).
    """
    districts = crosswalk_index.get(fips, [])
    if not districts:
        return None

    total_weight = sum(d["overlap_weight"] for d in districts)
    if total_weight == 0:
        return None

    weighted_sum = 0.0
    for d in districts:
        state_fips = d["district_state"]
        state_abbr = _state_fips_to_abbr(state_fips)
        state_tip = tipping_weights.get(state_abbr, state_tipping_weight)
        p1 = score_p1_presidential_formula(county_margin, state_tip)
        weighted_sum += p1 * d["overlap_weight"]

    return round(weighted_sum / total_weight, 2)


def calc_p2_alignment(fips, state_abbr, p2_state_index):
    """
    P2 Alignment: average key_vote_score of federal legislators from this state.
    Coverage = 'state_proxy' (House district field empty in federal_key_votes.csv,
    flagged by Agent C. Will be upgraded to district-level in Phase 3).
    """
    members = p2_state_index.get(state_abbr, [])
    if not members:
        return None, "unknown"
    scores = [m["key_vote_score"] for m in members]
    return round(sum(scores) / len(scores), 3), "state_proxy"


# FIPS (2-digit) → state abbreviation
_FIPS_TO_ABBR = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY", "72": "PR",
}


def _state_fips_to_abbr(fips_2):
    return _FIPS_TO_ABBR.get(fips_2, fips_2)


def classify_quadrant(sls_capital, p1_presidential, sls_threshold, p1_threshold):
    sls_high = sls_capital >= sls_threshold
    p1_high = p1_presidential >= p1_threshold
    if sls_high and p1_high:
        return "1_high_leverage_swing"
    elif sls_high and not p1_high:
        return "2_high_leverage_safe"
    elif not sls_high and p1_high:
        return "3_low_leverage_swing"
    else:
        return "4_lower_priority"


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--test", action="store_true", help="Run 50-county test sample")
    mode.add_argument("--full", action="store_true", help="Run all 3,143 counties")
    args = parser.parse_args()

    print("Loading data...")
    sr_data = load_json("data/processed/sector_reach_scores.json")
    sectors = sr_data["sectors"]

    emp_data = load_json("data/processed/county_sector_employment.json")
    employment = emp_data["employment"]

    crosswalk_rows = load_csv("data/processed/district_county_crosswalk.csv")
    key_vote_rows = load_csv("data/processed/federal_key_vote_scores.csv")
    tipping_weights = load_json("data/state_tipping_weights.json")
    weights = load_json("config/weights.json")
    thresholds = load_json("config/thresholds.json")

    # Load existing v2_test for P1 presidential (already correct, carry forward)
    v2_existing = load_json("data/county_scores_v2_test.json")
    existing_by_fips = {c["fips"]: c for c in v2_existing["counties"]}

    denominator = weights["svs_normalization"]["denominator"]
    p1_threshold = thresholds.get("sls", {}).get("p1_high", 5.0)
    sls_threshold_placeholder = 50.0  # will be recalibrated after full run

    print(f"Denominator: {denominator:,}")

    sector_points = build_sector_points(sectors, weights)
    crosswalk_index = build_crosswalk_index(crosswalk_rows)
    p2_state_index = build_p2_state_index(key_vote_rows)

    # Filter metadata keys from tipping_weights
    tipping_clean = {k: v for k, v in tipping_weights.items()
                     if not k.startswith("_")}

    all_fips = list(employment.keys())
    if args.test:
        # 50 counties: start with known spot-check targets, fill from existing v2_test
        spot_check_fips = ["06037", "42101", "42027", "56027", "53033"]
        filler = [c["fips"] for c in v2_existing["counties"]
                  if c["fips"] not in spot_check_fips][:45]
        fips_to_process = spot_check_fips + filler
        print(f"Test mode: {len(fips_to_process)} counties")
    else:
        fips_to_process = all_fips
        print(f"Full mode: {len(fips_to_process)} counties")

    results = []
    errors = []

    for fips in fips_to_process:
        try:
            county_sectors = employment.get(fips, {})
            existing = existing_by_fips.get(fips, {})

            state_abbr = existing.get("state", _state_fips_to_abbr(fips[:2]))
            state_tipping = tipping_clean.get(state_abbr, 0.0)
            county_margin = existing.get("margin_2024")

            sls_capital = calc_sls_capital(
                fips, county_sectors, sector_points, denominator
            )
            sls_community = calc_sls_community(
                fips, county_sectors, sector_points
            )

            # Carry forward p1_presidential — already real, do not recompute
            p1_presidential = existing.get("p1_presidential")
            if p1_presidential is None:
                p1_presidential = score_p1_presidential_formula(
                    county_margin, state_tipping
                )

            p1_congressional = calc_p1_congressional(
                fips, county_margin, state_tipping,
                crosswalk_index, tipping_clean
            )

            p2_alignment, p2_coverage = calc_p2_alignment(
                fips, state_abbr, p2_state_index
            )

            # Quadrant: use placeholder threshold for now (will recalibrate)
            quadrant = classify_quadrant(
                sls_capital, p1_presidential,
                sls_threshold_placeholder, p1_threshold
            )

            record = {
                "fips": fips,
                "county_name": existing.get("county_name", ""),
                "state": state_abbr,
                "region": existing.get("region", ""),
                "population": existing.get("population"),
                "swing_state": existing.get("swing_state"),
                "margin_2024": county_margin,
                "state_tipping_weight": state_tipping,
                "sls_capital": sls_capital,
                "sls_community": sls_community,
                "p1_presidential": p1_presidential,
                "p1_congressional": p1_congressional,
                "p2_alignment": p2_alignment,
                "p2_coverage": p2_coverage,
                "sls_high": sls_capital >= sls_threshold_placeholder,
                "p1_high": p1_presidential >= p1_threshold,
                "quadrant": quadrant,
                # Carry forward v1 fields for regression comparison
                "v1_organizing_opportunity_score": existing.get(
                    "v1_organizing_opportunity_score"
                ),
                "v1_sectoral_score": existing.get("v1_sectoral_score"),
                "v1_intervention_type": existing.get("v1_intervention_type"),
                "v1_priority_tier": existing.get("v1_priority_tier"),
                "_model_version": "2.0-true",
                "_sls_threshold_note": (
                    "sls_high threshold=50 is placeholder; "
                    "recalibrate after full run distribution review"
                ),
                "_generated": datetime.now(timezone.utc).isoformat(),
            }
            results.append(record)

        except Exception as e:
            errors.append({"fips": fips, "error": str(e)})

    output = {
        "_generated": datetime.now(timezone.utc).isoformat(),
        "_model_version": "2.0-true",
        "_source": "pipeline/build_v2_scores_true.py",
        "_counties_scored": len(results),
        "_errors": len(errors),
        "_denominator": denominator,
        "_note": (
            "True SLS scores. sls_high threshold is placeholder at 50; "
            "recalibrate after reviewing full distribution."
        ),
        "counties": results,
        "errors": errors,
    }

    if args.test:
        out_path = ROOT / "data" / "county_scores_v2_test_sample.json"
    else:
        out_path = ROOT / "data" / "county_scores_v2_test.json"

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {len(results)} counties to {out_path}")
    print(f"Errors: {len(errors)}")

    if errors:
        print("First 5 errors:")
        for e in errors[:5]:
            print(f"  {e['fips']}: {e['error']}")

    # Print spot check: 5 known counties
    known = {
        "06037": ("LA County", 100.0),
        "42101": ("Philadelphia", 100.0),
        "42027": ("Centre County PA", 10.56),
        "56027": ("Niobrara WY", 0.11),
        "53033": ("King County WA", 100.0),
    }
    by_fips = {r["fips"]: r for r in results}
    print("\n=== Spot Check: proxy vs true SLS-Capital ===")
    print(f"{'FIPS':<8} {'County':<22} {'Proxy':>8} {'True':>8} {'Community':>10} {'P1 Pres':>8} {'P1 Cong':>8} {'P2 Align':>10}")
    for fips, (name, proxy) in known.items():
        r = by_fips.get(fips)
        if r:
            p2 = f"{r['p2_alignment']:.3f}" if r["p2_alignment"] is not None else "N/A"
            p1c = f"{r['p1_congressional']:.2f}" if r["p1_congressional"] is not None else "N/A"
            print(f"{fips:<8} {name:<22} {proxy:>8.2f} {r['sls_capital']:>8.2f} "
                  f"{r['sls_community']:>10.2f} {r['p1_presidential']:>8.2f} "
                  f"{p1c:>8} {p2:>10}")
        else:
            print(f"{fips:<8} {name:<22} {proxy:>8.2f} {'NOT IN SAMPLE':>8}")

    if args.full:
        _print_distributions(results)


def _print_distributions(results):
    import statistics

    def dist(vals_raw, label):
        vals = sorted(v for v in vals_raw if v is not None)
        if not vals:
            print(f"{label}: no data")
            return
        n = len(vals)
        print(f"\n{label} (n={n:,}):")
        print(f"  min={vals[0]:.3f}  median={statistics.median(vals):.3f}  "
              f"p75={vals[int(n*0.75)]:.3f}  p90={vals[int(n*0.90)]:.3f}  "
              f"p95={vals[int(n*0.95)]:.3f}  max={vals[-1]:.3f}")

    print("\n" + "="*60)
    print("FULL RUN DISTRIBUTIONS")
    print("="*60)
    dist([r["sls_capital"] for r in results], "SLS-Capital")
    dist([r["sls_community"] for r in results], "SLS-Community")
    dist([r["p1_presidential"] for r in results], "P1 Presidential")
    dist([r["p1_congressional"] for r in results], "P1 Congressional")
    dist([r["p2_alignment"] for r in results], "P2 Alignment")

    quadrant_counts = defaultdict(int)
    for r in results:
        quadrant_counts[r["quadrant"]] += 1
    print("\nQuadrant distribution (sls_threshold=50 placeholder):")
    for q in sorted(quadrant_counts):
        print(f"  {q}: {quadrant_counts[q]}")

    # Propose SLS threshold
    sls_vals = sorted(r["sls_capital"] for r in results)
    n = len(sls_vals)
    p90 = sls_vals[int(n * 0.90)]
    p95 = sls_vals[int(n * 0.95)]
    print(f"\nFor top-10% threshold: p90 = {p90:.2f}")
    print(f"For top-5% threshold:  p95 = {p95:.2f}")
    print("NOTE: Sam must approve threshold before updating config/thresholds.json")


if __name__ == "__main__":
    main()
