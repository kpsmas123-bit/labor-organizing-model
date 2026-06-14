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

sys.path.insert(0, str(Path(__file__).parent.parent))
from scoring.electoral import classify_quadrant as _classify_quadrant_dual

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


# Reverse map: state abbreviation → 2-digit FIPS
_ABBR_TO_FIPS = {v: k for k, v in _FIPS_TO_ABBR.items()}


def _compute_tipping_weight(dem_seats, rep_seats, total_seats):
    """
    Chamber tipping weight: how close the chamber is to flipping majority.
    A chamber needing 1 seat to flip = maximum weight (close to 1.0).
    Formula: 1 - (seats_to_flip / total_seats)
    """
    if total_seats == 0:
        return 0.0
    majority_needed = total_seats // 2 + 1
    minority_seats = min(dem_seats, rep_seats)
    seats_to_flip = max(0, majority_needed - minority_seats)
    return round(max(0.0, 1.0 - seats_to_flip / total_seats), 4)


def compute_state_p1(state_abbr, chamber_data):
    """
    State P1 = average tipping weight across both chambers.
    Split chambers (weight near 1.0) = highest state leverage.
    """
    chambers = chamber_data.get("chambers", chamber_data)
    weights = []
    for chamber_key, data in chambers.items():
        if not chamber_key.startswith(f"{state_abbr}_"):
            continue
        tw = _compute_tipping_weight(
            data.get("dem_seats", 0),
            data.get("rep_seats", 0),
            data.get("total_seats", 0),
        )
        weights.append(tw)
    return round(sum(weights) / len(weights), 4) if weights else 0.0


def build_federal_p2_county_scores(legislators, crosswalk_rows, county_states):
    """
    Re-aggregate federal P2 from legislator level to county level.
    House: join via district-county crosswalk, weight by overlap_weight.
    Senate: apply to all counties in state, equal weight.

    Returns: {county_fips: federal_p2_score}
    """
    # Build crosswalk: district_geoid → list of {county_fips, overlap_weight}
    cw_index = defaultdict(list)
    for row in crosswalk_rows:
        cw_index[row["district_geoid"]].append({
            "county_fips": row["county_fips"],
            "overlap_weight": float(row["overlap_weight"]),
        })

    # Accumulate House scores per county: {fips: [weighted_p2, ...]}
    house_scores = defaultdict(list)
    for leg in legislators:
        if leg["chamber"] != "house":
            continue
        state_fips = _ABBR_TO_FIPS.get(leg["state"], "")
        district = str(leg["district"]).strip().zfill(2)
        geoid = f"{state_fips}{district}"
        p2 = leg.get("p2_combined")
        if p2 is None or p2 == "":
            continue
        p2 = float(p2)
        for entry in cw_index.get(geoid, []):
            house_scores[entry["county_fips"]].append(
                (p2, entry["overlap_weight"])
            )

    # Senate: all counties in state get the same average of both senators
    senate_by_state = defaultdict(list)
    for leg in legislators:
        if leg["chamber"] != "senate":
            continue
        p2 = leg.get("p2_combined")
        if p2 is None or p2 == "":
            continue
        senate_by_state[leg["state"]].append(float(p2))

    senate_avg_by_state = {
        state: sum(scores) / len(scores)
        for state, scores in senate_by_state.items()
    }

    # Combine House and Senate for each county
    county_p2 = {}
    all_fips = set(house_scores) | set(county_states)
    for fips in all_fips:
        state = county_states.get(fips)

        # House: overlap-weighted average
        house_entries = house_scores.get(fips, [])
        if house_entries:
            total_w = sum(w for _, w in house_entries)
            house_avg = (sum(p2 * w for p2, w in house_entries) / total_w
                         if total_w > 0 else None)
        else:
            house_avg = None

        senate_avg = senate_avg_by_state.get(state) if state else None

        scores = [s for s in [house_avg, senate_avg] if s is not None]
        if scores:
            county_p2[fips] = round(sum(scores) / len(scores), 4)

    return county_p2


def classify_quadrant(sls_capital, sls_community, p1_presidential,
                       cap_threshold, comm_threshold, p1_threshold):
    """v1.0 quadrant classification — kept for backward compat / existing quadrant field."""
    capital_high = sls_capital >= cap_threshold
    community_high = sls_community >= comm_threshold
    p1_high = p1_presidential >= p1_threshold
    both_high = capital_high and community_high

    if both_high and p1_high:
        return "deploy_now_both"
    elif capital_high and p1_high:
        return "deploy_now_capital"
    elif community_high and p1_high:
        return "deploy_now_community"
    elif capital_high:
        return "primary_target_capital"
    elif community_high:
        return "primary_target_community"
    elif p1_high:
        return "power_building"
    else:
        return "lower_priority"


def classify_quadrant_national(sls_capital, sls_community, p1_presidential,
                                federal_p2, thresholds):
    """National lens quadrant using P1 presidential + federal P2."""
    national_t = dict(thresholds["quadrant"])
    national_t["p1_high_boundary"] = national_t.get("p1_high_boundary", 5.0)
    return _classify_quadrant_dual(
        sls_capital, sls_community, p1_presidential, federal_p2, national_t
    )


def classify_quadrant_state(sls_capital, sls_community, state_p1,
                             state_p2, thresholds):
    """State lens quadrant using state P1 (tipping weight) + state P2."""
    state_t = dict(thresholds["quadrant"])
    state_t["p1_high_boundary"] = state_t.get("state_p1_high_boundary", 0.85)
    return _classify_quadrant_dual(
        sls_capital, sls_community, state_p1, state_p2, state_t
    )


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

    # Agent G: Load federal P2 (combined key votes + ideology)
    federal_p2_legislators = load_csv("data/processed/federal_p2_combined.csv")
    county_states = {c["fips"]: c.get("state", "") for c in v2_existing["counties"]}
    federal_p2_lookup = build_federal_p2_county_scores(
        federal_p2_legislators, crosswalk_rows, county_states
    )
    print(f"Federal P2 county scores built: {len(federal_p2_lookup)} counties")

    # Agent G: Load state P2
    state_p2_rows = load_csv("data/processed/state_p2_county_alignment.csv")
    state_p2_lookup = {
        str(r["fips"]).zfill(5): float(r["state_p2_score"])
        for r in state_p2_rows
        if r.get("state_p2_score") and r["state_p2_score"] != ""
    }
    print(f"State P2 county scores loaded: {len(state_p2_lookup)} counties")

    # Agent G: Load chamber tipping weights for state P1
    chamber_data = load_json("data/processed/chamber_seat_counts.json")

    denominator = weights["svs_normalization"]["denominator"]
    q = thresholds["quadrant"]
    cap_threshold = q["sls_capital_high_boundary"]
    comm_threshold = q["sls_community_high_boundary"]
    p1_threshold = q["p1_high_boundary"]

    print(f"Denominator: {denominator:,}")

    sector_points = build_sector_points(sectors, weights)
    crosswalk_index = build_crosswalk_index(crosswalk_rows)
    p2_state_index = build_p2_state_index(key_vote_rows)

    # Filter metadata keys from tipping_weights
    tipping_clean = {k: v for k, v in tipping_weights.items()
                     if not k.startswith("_")}

    all_fips = list(employment.keys())
    if args.test:
        # Agent G spot-check targets + filler to 50 counties
        spot_check_fips = [
            "42027",  # Centre County PA
            "55045",  # Green County WI
            "42101",  # Philadelphia PA
            "06037",  # LA County CA
            "04013",  # Maricopa AZ
            "13121",  # Fulton County GA
            "17031",  # Cook County IL
            "54061",  # Monongalia WV (Morgantown)
            "56027",  # Niobrara WY (prior spot-check)
            "53033",  # King County WA (prior spot-check)
        ]
        filler = [c["fips"] for c in v2_existing["counties"]
                  if c["fips"] not in spot_check_fips][:40]
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

            capital_high = sls_capital >= cap_threshold
            community_high = sls_community >= comm_threshold
            p1_high = p1_presidential >= p1_threshold
            quadrant = classify_quadrant(
                sls_capital, sls_community, p1_presidential,
                cap_threshold, comm_threshold, p1_threshold
            )

            # Agent G: Federal P2, State P2, State P1, dual-lens quadrants
            federal_p2 = federal_p2_lookup.get(fips)
            state_p2_raw = state_p2_lookup.get(fips)
            state_p2 = float(state_p2_raw) if state_p2_raw is not None else None
            state_p1 = compute_state_p1(state_abbr, chamber_data)

            quadrant_national = classify_quadrant_national(
                sls_capital, sls_community, p1_presidential, federal_p2, thresholds
            )
            quadrant_state = classify_quadrant_state(
                sls_capital, sls_community, state_p1, state_p2, thresholds
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
                "federal_p2": round(federal_p2, 4) if federal_p2 is not None else None,
                "state_p2": round(state_p2, 4) if state_p2 is not None else None,
                "state_p1": round(state_p1, 4),
                "quadrant_national": quadrant_national,
                "quadrant_state": quadrant_state,
                "capital_high": capital_high,
                "community_high": community_high,
                "p1_high": p1_high,
                "quadrant": quadrant,
                # Carry forward v1 fields for regression comparison
                "v1_organizing_opportunity_score": existing.get(
                    "v1_organizing_opportunity_score"
                ),
                "v1_sectoral_score": existing.get("v1_sectoral_score"),
                "v1_intervention_type": existing.get("v1_intervention_type"),
                "v1_priority_tier": existing.get("v1_priority_tier"),
                "_model_version": "2.0-true-agentG",
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
        "_thresholds": {
            "sls_capital_high": cap_threshold,
            "sls_community_high": comm_threshold,
            "p1_high": p1_threshold,
        },
        "_note": "True SLS scores. Dual-dimension quadrant classification (capital + community).",
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

    # Print spot check — Agent G dual-lens report
    spot_check_targets = [
        ("42027", "Centre County PA"),
        ("55045", "Green County WI"),
        ("42101", "Philadelphia PA"),
        ("06037", "LA County CA"),
        ("04013", "Maricopa AZ"),
        ("13121", "Fulton County GA"),
        ("17031", "Cook County IL"),
        ("54061", "Monongalia WV"),
    ]
    by_fips = {r["fips"]: r for r in results}
    print("\n=== Agent G Spot Check — Dual-Lens Quadrant ===")
    hdr = (f"{'FIPS':<8} {'County':<22} {'SLS-Cap':>7} {'SLS-Com':>7} "
           f"{'P1-Pres':>7} {'Fed-P2':>7} {'St-P1':>6} {'St-P2':>6} "
           f"{'Q-National':<28} {'Q-State':<28}")
    print(hdr)
    print("-" * len(hdr))
    for fips, name in spot_check_targets:
        r = by_fips.get(fips)
        if r:
            fp2 = f"{r['federal_p2']:.3f}" if r["federal_p2"] is not None else "N/A"
            sp2 = f"{r['state_p2']:.3f}" if r["state_p2"] is not None else "N/A"
            print(f"{fips:<8} {name:<22} "
                  f"{r['sls_capital']:>7.2f} {r['sls_community']:>7.2f} "
                  f"{r['p1_presidential']:>7.2f} {fp2:>7} {r['state_p1']:>6.3f} {sp2:>6} "
                  f"{r['quadrant_national']:<28} {r['quadrant_state']:<28}")
        else:
            print(f"{fips:<8} {name:<22} NOT IN SAMPLE")

    # Quadrant distribution summary for test sample
    from collections import Counter
    qn_dist = Counter(r["quadrant_national"] for r in results)
    qs_dist = Counter(r["quadrant_state"] for r in results)
    print("\n--- National lens quadrant distribution (test sample) ---")
    for q, n in sorted(qn_dist.items(), key=lambda x: -x[1]):
        print(f"  {q:<35} {n}")
    print("\n--- State lens quadrant distribution (test sample) ---")
    for q, n in sorted(qs_dist.items(), key=lambda x: -x[1]):
        print(f"  {q:<35} {n}")

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
    dist([r["p2_alignment"] for r in results], "P2 Alignment (legacy)")
    dist([r["federal_p2"] for r in results], "Federal P2 (combined)")
    dist([r["state_p2"] for r in results], "State P2 (DIME CFscore)")
    dist([r["state_p1"] for r in results], "State P1 (tipping weight)")

    total = len(results)

    null_fed_p2 = sum(1 for r in results if r["federal_p2"] is None)
    null_state_p2 = sum(1 for r in results if r["state_p2"] is None)
    print(f"\nNull federal_p2: {null_fed_p2} counties ({100*null_fed_p2/total:.1f}%)")
    print(f"Null state_p2:   {null_state_p2} counties ({100*null_state_p2/total:.1f}%)")

    # National lens distribution
    qn_counts = defaultdict(int)
    qs_counts = defaultdict(int)
    for r in results:
        qn_counts[r["quadrant_national"]] += 1
        qs_counts[r["quadrant_state"]] += 1

    print("\nNational lens quadrant distribution:")
    for cat, n in sorted(qn_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:<35} {n:>5}  ({100*n/total:.1f}%)")

    print("\nState lens quadrant distribution:")
    for cat, n in sorted(qs_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:<35} {n:>5}  ({100*n/total:.1f}%)")

    # Tier 1 counties (the most important output)
    tier1 = [r for r in results if r["quadrant_national"].startswith("tier1_")]
    print(f"\nTier 1 national counties ({len(tier1)}):")
    for r in sorted(tier1, key=lambda x: -(x["p1_presidential"] or 0))[:30]:
        fp2 = f"{r['federal_p2']:.3f}" if r["federal_p2"] is not None else "N/A"
        print(f"  {r['fips']} {r['county_name']:<25} {r['state']}  "
              f"P1={r['p1_presidential']:>6.2f}  P2={fp2}  {r['quadrant_national']}")

    # Legacy quadrant distribution
    order = [
        "deploy_now_both", "deploy_now_capital", "deploy_now_community",
        "primary_target_capital", "primary_target_community",
        "power_building", "lower_priority",
    ]
    quadrant_counts = defaultdict(int)
    for r in results:
        quadrant_counts[r["quadrant"]] += 1
    print("\nLegacy quadrant distribution (v1.0 fields — for regression):")
    for cat in order:
        n = quadrant_counts.get(cat, 0)
        print(f"  {cat:<30} {n:>5}  ({100*n/total:.1f}%)")


if __name__ == "__main__":
    main()
