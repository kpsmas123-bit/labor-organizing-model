"""
Terrain v2.0 — CANONICAL build (real P2 + dual lens + 6-tier classification).

Supersedes pipeline/build_v2_scores_true.py (which only emitted single-lens
quadrants and a state-proxy P2). This script wires in the Agent E/F/G data that
was produced but never connected:

  * Real FEDERAL P2  = key_vote_score*0.60 + inverse_ideology*0.40, aggregated to
    county by district overlap (source: data/processed/federal_p2_combined.csv,
    where p2_combined already encodes the 0.60/0.40 weighting per legislator).
  * Real STATE P2    = DIME CFscore + party-imputed state alignment, per county
    (source: data/processed/state_p2_county_alignment.csv).
  * Dual lens        = National (presidential tipping + federal P2) and
                       State (chamber tipping + state P2). SLS is identical in
                       both lenses; only P1 and P2 change.
  * 6-tier P2-driven classification, run once per lens.

SLS-Capital / SLS-Community / the P1 formula are UNCHANGED — reproduced exactly
from build_v2_scores_true.py. See BUILD_PROGRESS.md for every non-trivial
decision (CT/FIPS reconciliation, BUG #1 fix, state-P1 scale caveat).

Output: data/county_scores.json  (v1 backed up to data/archive/ first).

Run:
  python pipeline/build_v2_canonical.py --full   (all 3,143 counties)
  python pipeline/build_v2_canonical.py --test    (50-county sample, no overwrite)
"""

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent

# B1: BOTH SLS paths now weight each sector by the FULL composite SVS (svs.py),
# not bare cap/comm reach. Import the canonical SVS scorer so the weight is the
# SAME unified composite used everywhere (single source: scoring/svs.py).
sys.path.insert(0, str(ROOT / "scoring"))
from svs import score_svs  # noqa: E402

# P1 formula constants (identical to scoring/electoral.py / build_v2_scores_true.py)
_MIN_MARGIN_PP = 0.5
_NORM = 100.0 / 0.28          # 357.14 — calibrates PA (0.28) competitive counties to ~100
_PRES_DEFAULT_TIP = 0.005     # _default from state_tipping_weights.json (BUG #1 fix: stored == used)

# FIPS (2-digit) -> state abbreviation
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


def load_json(rel):
    with open(ROOT / rel) as f:
        return json.load(f)


def load_csv(rel):
    with open(ROOT / rel) as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- SLS (B1: full composite SVS)

def build_sector_svs(sectors, weights):
    """
    B1: ONE unified composite SVS per sector, used by BOTH SLS paths.

    composite_svs(sector) = the FULL svs.py formula —
        reach(cap) + reach(comm) + community_facing + non_offshorability
        + dual_crisis_bonus + whole_worker_bonus
    using the SAME svs_formula weights in config/weights.json. Replaces the old
    per-path bare-reach weight (cap_reach for Capital, comm_reach for Community).
    The Capital/Community distinction is now carried ENTIRELY by gross-vs-density
    (employment vs employment-share), NOT by tilting the per-sector weight.

    Returns: sid -> composite_svs (float, ~10-60).
    """
    svs_w = weights["svs_formula"]
    return {
        sid: score_svs(s["cap_reach"], s["comm_reach"], s["comm_facing"], s["non_off"], svs_w)
        for sid, s in sectors.items()
    }


def calc_sls_capital(county_sectors, sector_svs, divisor):
    """MAGNITUDE: raw = Σ_sector(composite_svs × employment); capped at 100 after /divisor."""
    raw = sum(sector_svs[sid] * emp["total_employment"]
              for sid, emp in county_sectors.items() if sid in sector_svs)
    return round(min(100.0, raw / divisor), 2)


def confidence_ramp(total_emp, ramp):
    """
    Soft employment-confidence ramp (DATA-RELIABILITY NOISE GATE, state-agnostic).
    Returns a multiplier in [0, 1]: 1.0 at/above ramp_full_at, 0.0 at/below
    ramp_zero_at, linear in between. Params are READ FROM CONFIG, not hardcoded.
    """
    full_at = ramp["ramp_full_at"]
    zero_at = ramp["ramp_zero_at"]
    if total_emp >= full_at:
        return 1.0
    if total_emp <= zero_at:
        return 0.0
    return (total_emp - zero_at) / (full_at - zero_at)


def calc_sls_community(county_sectors, sector_svs, community_mult, ramp):
    """
    CONCENTRATION: weighted = Σ_sector(composite_svs × employment-share); the SAME
    unified composite_svs as Capital — only gross-vs-density differs.
      share_score = min(100, weighted × community_mult)   (community_mult is config-driven, B1)
      SLS-Community = min(100, share_score × confidence_ramp)   (Option D ramp unchanged)
    """
    total = sum(e["total_employment"] for e in county_sectors.values())
    if total == 0:
        return 0.0
    weighted = sum(sector_svs[sid] * (emp["total_employment"] / total)
                   for sid, emp in county_sectors.items() if sid in sector_svs)
    share_score = min(100.0, weighted * community_mult)   # B1: config-driven (was hardcoded ×4)
    # Option D: gate the share signal by a soft employment-confidence ramp.
    return round(min(100.0, share_score * confidence_ramp(total, ramp)), 2)


# ---------------------------------------------------------------- P1 (unchanged formula)

def score_p1(county_margin, tipping_weight):
    """Continuous P1 = tipping_weight * (1/abs(margin)), normalized, capped 100."""
    if county_margin is None:
        return 15.0
    if tipping_weight is None:
        return None
    abs_margin = max(_MIN_MARGIN_PP, abs(county_margin))
    raw = tipping_weight * (1.0 / abs_margin)
    return round(min(100.0, raw * _NORM), 2)


def build_chamber_tipping(chamber_data):
    """state_abbr -> averaged chamber tipping weight (1 - seats_from_flip/total)."""
    per_state = defaultdict(list)
    for key, c in chamber_data.items():
        state = key.split("_")[0]
        total = c["total_seats"]
        if not total:
            continue
        seats_from_flip = abs(c["dem_seats"] - c["rep_seats"]) / 2.0
        per_state[state].append(1.0 - seats_from_flip / total)
    return {s: round(sum(v) / len(v), 4) for s, v in per_state.items()}


# ---------------------------------------------------------------- Federal P2 (real)

def build_federal_p2_indexes(p2_rows):
    """
    Returns:
      house_by_key  : (state_abbr, district_int) -> p2_combined
      house_by_state: state_abbr -> [p2_combined, ...]  (statewide fallback)
      senate_by_state: state_abbr -> [p2_combined, ...]
    Source already excludes deceased/former members (e.g. Feinstein).
    """
    house_by_key, house_by_state, senate_by_state = {}, defaultdict(list), defaultdict(list)
    for r in p2_rows:
        p2 = r.get("p2_combined", "")
        if p2 == "":
            continue
        p2 = float(p2)
        st = r["state"]
        if r["chamber"] == "senate":
            senate_by_state[st].append(p2)
        elif r["chamber"] == "house":
            dist = r["district"].strip()
            if dist:
                house_by_key[(st, int(dist))] = p2
            house_by_state[st].append(p2)
    return house_by_key, dict(house_by_state), dict(senate_by_state)


def build_crosswalk_index(rows):
    """county_fips -> [(state_abbr, district_int, overlap_weight)]"""
    idx = defaultdict(list)
    for r in rows:
        idx[r["county_fips"]].append((
            _FIPS_TO_ABBR.get(r["district_state"], r["district_state"]),
            int(r["district_number"]),
            float(r["overlap_weight"]),
        ))
    return dict(idx)


def calc_federal_p2(fips, state_abbr, crosswalk_idx,
                    house_by_key, house_by_state, senate_by_state):
    """
    Pooled overlap-weighted average of p2_combined: House members weighted by
    district overlap, Senators weighted 1.0 each. Crosswalk-miss counties (e.g.
    CT's planning-region FIPS) fall back to the statewide House delegation.
    Returns (p2 or None, coverage_flag).
    """
    house_items, used_district = [], False
    for (abbr, dist, w) in crosswalk_idx.get(fips, []):
        p2 = house_by_key.get((abbr, dist))
        if p2 is not None:
            house_items.append((p2, w))
            used_district = True

    house_mode = None
    if house_items:
        house_mode = "district"
    elif state_abbr in house_by_state:                  # crosswalk miss -> statewide fallback
        house_items = [(p2, 1.0) for p2 in house_by_state[state_abbr]]
        house_mode = "statewide"

    sens = senate_by_state.get(state_abbr, [])
    pool = house_items + [(p2, 1.0) for p2 in sens]
    if not pool:
        return None, "unknown"

    tw = sum(w for _, w in pool)
    p2 = round(sum(p * w for p, w in pool) / tw, 3)

    if house_mode == "district":
        cov = "house_and_senate" if sens else "house_only"
    elif house_mode == "statewide":
        cov = "house_and_senate_statewide" if sens else "house_only_statewide"
    else:
        cov = "senate_only"
    return p2, cov


# ---------------------------------------------------------------- State P2 (real)

def build_state_p2_index(rows):
    """state_abbr -> (score, coverage). Source is state-uniform per BUILD_PROGRESS Step 1."""
    out = {}
    for r in rows:
        st = r["state"]
        if st not in out:
            out[st] = (float(r["state_p2_score"]), r["coverage_type"])
    return out


# ---------------------------------------------------------------- 6-tier classification

def classify(sls_capital, sls_community, p1, p2, T):
    """
    P2-driven 6-tier classification (one lens). Emits the exact quadrant strings
    the map frontend expects (tier1_*, tier2_activate/build/unknown_*, tier3_electoral, tier4).
    """
    capital_high = sls_capital >= T["sls_capital"]
    community_high = sls_community >= T["sls_community"]
    sls_high = capital_high or community_high
    p1_high = (p1 is not None) and (p1 >= T["p1"])

    if not sls_high:
        return "tier3_electoral" if p1_high else "tier4"

    # SLS is high — pick the dimension suffix (preserve capital/community split)
    both = capital_high and community_high
    dim = "capital" if capital_high else "community"

    if not p1_high:                                     # Tier 2 — Build
        return f"tier2_build_{dim}"

    # high SLS + high P1 — split by P2
    if p2 is None:
        return f"tier2_unknown_{dim}"
    if p2 < T["p2_hostile"]:                            # Tier 1 — Transform
        return f"tier1_{'capital_community' if both else dim}"
    if p2 >= T["p2_aligned"]:                           # Tier 2 — Activate
        return f"tier2_activate_{dim}"
    return f"tier2_unknown_{dim}"                       # Tier 2 — Unknown (neutral)


def classify_national(sls_capital, sls_community, p1, state_tipping_weight, T):
    """
    NATIONAL-lens classifier (whole-worker reframe, 2026-06-16). The two leverage
    types reach Tier 1 by DIFFERENT rules, and P2 is REMOVED from BOTH national
    pathways (decisiveness compounds regardless of incumbent posture):

      * National Capital Tier-1   = capital_high AND p1_high (p1_national >= the
        existing 5.0 gate). Decisiveness kept; no P2.
      * National Community Tier-1 = community_high AND the state is electorally
        DECISIVE at the top level, GRADED by the continuous presidential
        decisiveness signal state_tipping_weight:
            swing  (stw >= stw_high)               -> Tier 1 community
            lean   (stw_moderate <= stw < stw_high) -> Tier 2 community (build/activate)
            locked (stw < stw_moderate)            -> lower tiers
        No P2, no county-level p1 (community's electoral value is statewide).

    Everything that does not clear Tier 1 falls through the existing
    tier2/tier3/tier4 cascade using the SAME label strings as the shared classifier.
    P2-driven sublabels (activate/unknown) do not appear on the national lens by
    construction, since national no longer reads P2.
    """
    capital_high = sls_capital >= T["sls_capital"]
    community_high = sls_community >= T["sls_community"]
    p1_high = (p1 is not None) and (p1 >= T["p1"])
    stw = state_tipping_weight
    swing = (stw is not None) and (stw >= T["stw_high"])
    lean = (stw is not None) and (T["stw_moderate"] <= stw < T["stw_high"])

    # --- Tier 1: two pathways, NO P2 ---
    cap_t1 = capital_high and p1_high
    comm_t1 = community_high and swing
    if cap_t1 and comm_t1:
        return "tier1_capital_community"
    if cap_t1:
        return "tier1_capital"
    if comm_t1:
        return "tier1_community"

    # --- Tier 2 (did not clear Tier 1) — preserve existing labels ---
    if capital_high:                       # capital_high but p1 not high -> Build
        return "tier2_build_capital"
    if community_high and lean:            # community_high + moderate decisiveness -> Build/Activate
        return "tier2_build_community"

    # community_high but locked, or no high SLS -> lower tiers
    return "tier3_electoral" if p1_high else "tier4"


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    m = ap.add_mutually_exclusive_group(required=True)
    m.add_argument("--full", action="store_true")
    m.add_argument("--test", action="store_true")
    args = ap.parse_args()

    print("Loading inputs...")
    sectors = load_json("data/processed/sector_reach_scores.json")["sectors"]
    emp_data = load_json("data/processed/county_sector_employment.json")
    employment = emp_data["employment"]
    weights = load_json("config/weights.json")
    thresholds = load_json("config/thresholds.json")
    pres_tip = {k: v for k, v in load_json("data/state_tipping_weights.json").items()
                if not k.startswith("_")}
    chamber_tip = build_chamber_tipping(
        load_json("data/processed/chamber_seat_counts.json")["chambers"])

    fed_rows = load_csv("data/processed/federal_p2_combined.csv")
    house_key, house_state, senate_state = build_federal_p2_indexes(fed_rows)
    crosswalk_idx = build_crosswalk_index(
        load_csv("data/processed/district_county_crosswalk.csv"))
    state_p2_idx = build_state_p2_index(
        load_csv("data/processed/state_p2_county_alignment.csv"))

    v2_existing = load_json("data/county_scores_v2_test.json")
    existing = {c["fips"]: c for c in v2_existing["counties"]}

    denominator = weights["svs_normalization"]["denominator"]            # capital divisor (B1: 750000)
    community_mult = weights["svs_normalization"]["community_multiplier"]  # B1: config-driven (was ×4 hardcode)
    sls_comm_ramp = thresholds["sls_community_confidence_ramp"]  # Option D noise gate (config-read)
    q = thresholds["quadrant"]
    T = {
        "sls_capital": q["sls_capital_high_boundary"],
        "sls_community": q["sls_community_high_boundary"],
        "p1": q["p1_high_boundary"],
        "p2_hostile": q["p2_hostile_ceiling"],
        "p2_aligned": q["p2_aligned_floor"],
        # national community Tier-1 grading by presidential state-decisiveness
        "stw_high": q["state_tipping_swing_floor"],
        "stw_moderate": q["state_tipping_lean_floor"],
    }
    sector_svs = build_sector_svs(sectors, weights)   # B1: one unified composite SVS per sector

    all_fips = sorted(employment.keys())
    fips_list = all_fips if args.full else all_fips[:50]
    print(f"Scoring {len(fips_list)} counties...")

    results, errors = [], []
    for fips in fips_list:
        try:
            ex = existing.get(fips, {})
            state_abbr = ex.get("state") or _FIPS_TO_ABBR.get(fips[:2], fips[:2])
            margin = ex.get("margin_2024")
            county_sectors = employment.get(fips, {})

            sls_capital = calc_sls_capital(county_sectors, sector_svs, denominator)
            sls_community = calc_sls_community(county_sectors, sector_svs, community_mult, sls_comm_ramp)

            # --- P1: national (presidential) + state (chamber). BUG #1: default applied to both. ---
            pres_w = pres_tip.get(state_abbr, _PRES_DEFAULT_TIP)
            p1_national = score_p1(margin, pres_w)
            cham_w = chamber_tip.get(state_abbr)                  # None for DC, DE
            p1_state = score_p1(margin, cham_w) if cham_w is not None else None

            # --- P2: federal (national) + state ---
            p2_national, p2_cov = calc_federal_p2(
                fips, state_abbr, crosswalk_idx, house_key, house_state, senate_state)
            if state_abbr in state_p2_idx:
                p2_state, state_p2_cov = state_p2_idx[state_abbr]
            else:
                p2_state, state_p2_cov = None, "no_state_legislature"

            quadrant_national = classify_national(sls_capital, sls_community,
                                                  p1_national, pres_w, T)
            quadrant_state = classify(sls_capital, sls_community, p1_state, p2_state, T)

            results.append({
                "fips": fips,
                "county_name": ex.get("county_name", ""),
                "state": state_abbr,
                "region": ex.get("region", ""),
                "population": ex.get("population"),
                "swing_state": ex.get("swing_state"),
                "margin_2024": margin,
                "state_tipping_weight": pres_w,            # BUG #1: now consistent with p1_national
                "chamber_tipping_weight": cham_w,
                "sls_capital": sls_capital,
                "sls_community": sls_community,
                # dual lens — canonical fields
                "p1_national": p1_national,
                "p2_national": p2_national,
                "p1_state": p1_state,
                "p2_state": p2_state,
                "p2_coverage": p2_cov,
                "state_p2_coverage": state_p2_cov,
                "quadrant_national": quadrant_national,
                "quadrant_state": quadrant_state,
                # backward-compat aliases (older JS reads these)
                "p1_presidential": p1_national,
                "p2_alignment": p2_national,
                "federal_p2": p2_national,
                "quadrant": quadrant_national,
                # v1 regression fields
                "v1_organizing_opportunity_score": ex.get("v1_organizing_opportunity_score"),
                "v1_sectoral_score": ex.get("v1_sectoral_score"),
                "v1_intervention_type": ex.get("v1_intervention_type"),
                "v1_priority_tier": ex.get("v1_priority_tier"),
                "_model_version": "2.0",
            })
        except Exception as e:
            errors.append({"fips": fips, "error": repr(e)})

    nat_counts = defaultdict(int)
    st_counts = defaultdict(int)
    for r in results:
        nat_counts[r["quadrant_national"]] += 1
        st_counts[r["quadrant_state"]] += 1

    output = {
        "_generated": datetime.now(timezone.utc).isoformat(),
        "_model_version": "2.0",
        "_source": "pipeline/build_v2_canonical.py",
        "_counties_scored": len(results),
        "_errors": len(errors),
        "_denominator": denominator,
        "_community_multiplier": community_mult,
        "_sls_weight": "B1: full composite SVS (svs.py) per sector, unified across both paths",
        "_thresholds": T,
        "_tier_counts_national": dict(nat_counts),
        "_tier_counts_state": dict(st_counts),
        "_note": "Terrain v2.0 canonical. Real federal + state P2, dual lens, 6-tier P2-driven classification.",
        "counties": results,
        "errors": errors,
    }

    out_path = ROOT / "data" / ("county_scores.json" if args.full
                                else "data/county_scores_v2canon_test.json".split("/")[-1])
    if args.full:
        # back up v1 before overwriting
        archive = ROOT / "data" / "archive"
        archive.mkdir(exist_ok=True)
        backup = archive / "county_scores_v1_2026-05-17.json"
        if not backup.exists():
            shutil.copy2(ROOT / "data" / "county_scores.json", backup)
            print(f"Backed up v1 -> {backup}")

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {len(results)} counties -> {out_path}  (errors: {len(errors)})")

    print("\nNational tier counts:")
    for k in sorted(nat_counts):
        print(f"  {k:<28} {nat_counts[k]:>5}")
    print("State tier counts:")
    for k in sorted(st_counts):
        print(f"  {k:<28} {st_counts[k]:>5}")
    if errors:
        print("\nFirst errors:", errors[:5])


if __name__ == "__main__":
    main()
