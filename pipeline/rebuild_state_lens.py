"""
State-lens rebuild (Agent 1, Phase 2).

Surgically recomputes ONLY the state-lens fields of data/county_scores.json:
  * p1_state            competitiveness x chamber-flip proximity  (recalibrated)
  * p2_state            party proxy (county-resolved, overlap-weighted Dem share)
  * quadrant_state      existing 6-tier classifier on state-lens inputs
  * state_p2_coverage   = party_proxy (or party_proxy_state_uniform fallback)
  * p1_state_data_tier  NEW: confidence of the margin (district_actual / presidential)
  * margin_stale        NEW (state lens): carried from competitiveness file
  * state_noncomp_priority  NEW: low-P1 alignment subdivision (hostile/neutral/aligned)

National fields and SLS are NOT touched. The classifier is the EXISTING
classify() from build_v2_canonical.py, run with a state-specific p1 threshold.

DESIGN (see STATE_LENS_REBUILD_PROGRESS.md for full rationale):

  P1_state = 100 * chamber_flip_proximity * comp(margin)
    comp(margin)            = max(0, (BAND - |margin|) / BAND),  BAND = 8.0pp
    chamber_flip_proximity  = tipping_weights[<state>_<chamber of most-competitive seat>]
                              (1 - seats_from_flip/total_seats; near-tie -> ~1.0)
                              fallback: state-mean chamber proximity (presidential-tier
                              counties have no named seat); None for DC/DE (no chamber data)
    -> bounded [0, ~98]; NO 1/margin blow-up. p1_high_state threshold added to thresholds.json.

  P2_state = overlap-weighted Democratic share of the county's CURRENT state-leg
             representation, from data/work_stateleg/county_seat_detail.json
             (current_party x share). 0 = all-R (hostile), 1 = all-D (aligned),
             on the same 0-1 scale as federal P2. Counties with no resolvable
             overlap fall back to the state-uniform legislative Dem share (flagged).

  Overlay: if data/processed/state_leg_competitiveness_backfill.csv exists, its rows
           REPLACE base rows by fips (higher-confidence gubernatorial/state-returns).

Run:
  python pipeline/rebuild_state_lens.py --write   (overwrite county_scores.json, backup first)
  python pipeline/rebuild_state_lens.py           (dry-run: print distribution only)
"""

import argparse
import csv
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from build_v2_canonical import classify  # reuse the EXISTING 6-tier classifier

ROOT = Path(__file__).parent.parent

BAND = 8.0  # competitive width (pp). Widened from the ~3% convention for gradation.

COMP_PATH = ROOT / "data/processed/state_leg_competitiveness.csv"
OVERLAY_PATH = ROOT / "data/processed/state_leg_competitiveness_backfill.csv"
SEAT_DETAIL_PATH = ROOT / "data/work_stateleg/county_seat_detail.json"
CHAMBER_PATH = ROOT / "data/processed/chamber_seat_counts.json"
SCORES_PATH = ROOT / "data/county_scores.json"
THRESHOLDS_PATH = ROOT / "config/thresholds.json"


# --------------------------------------------------------------- inputs

def load_competitiveness():
    """fips -> row. Overlay rows (if present) REPLACE base rows by fips."""
    base = {r["fips"]: r for r in csv.DictReader(open(COMP_PATH))}
    overlay_found = False
    if OVERLAY_PATH.exists():
        overlay_found = True
        for r in csv.DictReader(open(OVERLAY_PATH)):
            base[r["fips"]] = r  # higher-confidence row wins
    return base, overlay_found


def build_chamber_proximity(chamber_json):
    """
    Returns:
      by_chamber : '<ST>_house' / '<ST>_senate' -> proximity (0..1)
      by_state   : '<ST>' -> mean proximity across that state's chambers
      state_dem_share : '<ST>' -> Dem share of all legislative seats (state-uniform P2 fallback)
    """
    tw = chamber_json["tipping_weights"]
    chs = chamber_json["chambers"]
    by_state = defaultdict(list)
    for k, v in tw.items():
        by_state[k.split("_")[0]].append(v)
    state_mean = {s: sum(v) / len(v) for s, v in by_state.items()}

    seat_dem = defaultdict(lambda: [0, 0])  # state -> [dem, total]
    for k, c in chs.items():
        st = k.split("_")[0]
        seat_dem[st][0] += c.get("dem_seats", 0)
        seat_dem[st][1] += c.get("total_seats", 0)
    state_dem_share = {s: (d / t if t else None) for s, (d, t) in seat_dem.items()}
    return tw, state_mean, state_dem_share


_SEAT_RE = re.compile(r"seat=([A-Z]{2})-([LU])")


def best_seat_chamber(source):
    """Most-competitive seat's chamber from the competitiveness source string."""
    m = _SEAT_RE.search(source or "")
    if not m:
        return None
    abbr, lu = m.group(1), m.group(2)
    return abbr, ("house" if lu == "L" else "senate")


# --------------------------------------------------------------- P1_state

def comp_signal(margin):
    if margin is None:
        return 0.0
    return max(0.0, (BAND - abs(margin)) / BAND)


def proximity_for(row, tw, state_mean):
    """Chamber-flip proximity for a county. None when the state has no chamber data."""
    bs = best_seat_chamber(row.get("source", ""))
    if bs:
        key = f"{bs[0]}_{bs[1]}"
        if key in tw:
            return tw[key]
    return state_mean.get(row["state"])  # presidential-tier / unnamed-seat fallback


def score_p1_state(row, tw, state_mean):
    try:
        margin = float(row["margin"])
    except (TypeError, ValueError):
        margin = None
    prox = proximity_for(row, tw, state_mean)
    if prox is None or margin is None:
        return 0.0, prox  # DC/DE (no chamber data) or no margin -> floor
    return round(100.0 * prox * comp_signal(margin), 2), prox


# --------------------------------------------------------------- P2_state

def score_p2_state(fips, seat_detail, state_abbr, state_dem_share):
    """
    Overlap-weighted Dem share from CURRENT state-leg roster.
    Returns (p2 in 0..1, coverage_flag).
    None party seats are excluded from the denominator (unknown);
    Independents count toward the denominator but not the Dem numerator.
    """
    seats = seat_detail.get(fips, [])
    dem = sum(s.get("share", 0) for s in seats if s.get("current_party") == "D")
    denom = sum(s.get("share", 0) for s in seats
                if s.get("current_party") in ("D", "R", "I"))
    if denom > 0:
        return round(dem / denom, 4), "party_proxy"
    # fallback: state-uniform legislative Dem share
    su = state_dem_share.get(state_abbr)
    if su is not None:
        return round(su, 4), "party_proxy_state_uniform"
    return 0.5, "party_proxy_unavailable"  # last resort (e.g. DC) — neutral, flagged


# --------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="overwrite data/county_scores.json (backs up first)")
    args = ap.parse_args()

    comp, overlay_found = load_competitiveness()
    seat_detail = json.load(open(SEAT_DETAIL_PATH))
    chamber_json = json.load(open(CHAMBER_PATH))
    tw, state_mean, state_dem_share = build_chamber_proximity(chamber_json)
    thresholds = json.load(open(THRESHOLDS_PATH))
    scores = json.load(open(SCORES_PATH))

    q = thresholds["quadrant"]
    # State-lens thresholds: SLS + P2 identical to national; ONLY p1 differs (scale differs).
    T_state = {
        "sls_capital": q["sls_capital_high_boundary"],
        "sls_community": q["sls_community_high_boundary"],
        "p1": q["p1_high_state"],          # NEW state-specific threshold
        "p2_hostile": q["p2_hostile_ceiling"],
        "p2_aligned": q["p2_aligned_floor"],
    }

    canon_fips = {c["fips"] for c in scores["counties"]}
    comp_not_canon = sorted(set(comp) - canon_fips)
    canon_not_comp = sorted(canon_fips - set(comp))

    log = {
        "overlay_found": overlay_found,
        "band": BAND,
        "p1_high_state": T_state["p1"],
        "comp_rows_not_in_canonical": comp_not_canon,
        "canonical_not_in_comp": canon_not_comp,
        "p2_fallback_state_uniform": [],
        "p2_unavailable": [],
        "p1_floor_no_chamber": [],
        "national_sample_before": None,
        "national_sample_after": None,
    }

    # snapshot national fields of a sample county to prove they're untouched
    sample = scores["counties"][0]
    nat_keys = ["p1_national", "p2_national", "p1_presidential", "p2_alignment",
                "federal_p2", "quadrant_national", "quadrant", "sls_capital", "sls_community"]
    log["national_sample_before"] = {k: sample.get(k) for k in nat_keys}

    st_counts = defaultdict(int)
    sub_counts = defaultdict(int)
    for c in scores["counties"]:
        fips = c["fips"]
        state_abbr = c["state"]
        row = comp.get(fips, {"state": state_abbr, "margin": None, "source": "",
                              "p1_data_tier": "missing", "margin_stale": "False"})

        p1_state, prox = score_p1_state(row, tw, state_mean)
        if prox is None:
            log["p1_floor_no_chamber"].append(fips)

        p2_state, p2_cov = score_p2_state(fips, seat_detail, state_abbr, state_dem_share)
        if p2_cov == "party_proxy_state_uniform":
            log["p2_fallback_state_uniform"].append(fips)
        elif p2_cov == "party_proxy_unavailable":
            log["p2_unavailable"].append(fips)

        quadrant_state = classify(c["sls_capital"], c["sls_community"],
                                  p1_state, p2_state, T_state)

        # --- ENHANCEMENT: subdivide the NON-competitive (low-P1) band by alignment ---
        # Additive only; does NOT alter quadrant_state. hostile > neutral > aligned priority.
        p1_high = p1_state >= T_state["p1"]
        if not p1_high:
            if p2_state < q["p2_hostile_ceiling"]:
                sub = "hostile"
            elif p2_state >= q["p2_aligned_floor"]:
                sub = "aligned"
            else:
                sub = "neutral"
        else:
            sub = None  # high-P1 tiers untouched
        sub_counts[sub] += 1

        # write ONLY state-lens fields
        c["p1_state"] = p1_state
        c["p2_state"] = p2_state
        c["state_p2_coverage"] = p2_cov
        c["p1_state_data_tier"] = row.get("p1_data_tier", "missing")
        c["margin_stale"] = (str(row.get("margin_stale", "False")).lower() == "true")
        c["quadrant_state"] = quadrant_state
        c["state_noncomp_priority"] = sub

        st_counts[quadrant_state] += 1

    log["national_sample_after"] = {k: sample.get(k) for k in nat_keys}

    # update metadata block
    scores["_tier_counts_state"] = dict(st_counts)
    scores["_state_lens_rebuild"] = {
        "rebuilt": datetime.now(timezone.utc).isoformat(),
        "formula": "P1_state=100*chamber_flip_proximity*max(0,(BAND-|margin|)/BAND); "
                   "P2_state=overlap-weighted Dem share of current state-leg roster (party_proxy)",
        "band": BAND,
        "p1_high_state": T_state["p1"],
        "overlay_found": overlay_found,
        "p2_fallback_count": len(log["p2_fallback_state_uniform"]),
        "noncomp_subdivision": dict(sub_counts),
    }

    print("== STATE-LENS REBUILD ==")
    print(f"overlay_found: {overlay_found}")
    print(f"comp rows not in canonical (logged, not force-fit): {log['comp_rows_not_in_canonical']}")
    print(f"canonical not in comp: {log['canonical_not_in_comp']}")
    print(f"P2 state-uniform fallbacks: {len(log['p2_fallback_state_uniform'])}")
    print(f"P2 unavailable (neutral 0.5): {log['p2_unavailable']}")
    print(f"P1 floor (no chamber data): {len(log['p1_floor_no_chamber'])} -> "
          f"{sorted({f[:2] for f in log['p1_floor_no_chamber']})}")
    print("\nNew state tier counts:")
    for k in sorted(st_counts):
        print(f"  {k:<28} {st_counts[k]:>5}")
    print("\nNon-competitive (low-P1) alignment subdivision:")
    for k in sorted(sub_counts, key=lambda x: (x is None, x)):
        print(f"  {str(k):<12} {sub_counts[k]:>5}")
    n_high = sum(1 for c in scores["counties"] if c["p1_state"] >= T_state["p1"])
    print(f"\nCounties above p1_high_state ({T_state['p1']}): "
          f"{n_high} ({n_high/len(scores['counties'])*100:.1f}%)")
    print(f"National sample fields unchanged: "
          f"{log['national_sample_before'] == log['national_sample_after']}")

    if args.write:
        archive = ROOT / "data" / "archive"
        archive.mkdir(exist_ok=True)
        stamp = "county_scores_pre_state_lens_rebuild.json"
        backup = archive / stamp
        if not backup.exists():
            shutil.copy2(SCORES_PATH, backup)
            print(f"\nBacked up -> {backup}")
        with open(SCORES_PATH, "w") as f:
            json.dump(scores, f, indent=2)
        with open(ROOT / "data" / "work_stateleg" / "state_lens_rebuild_log.json", "w") as f:
            json.dump(log, f, indent=2)
        print(f"Wrote state-lens fields -> {SCORES_PATH}")
    else:
        print("\n(dry-run; pass --write to persist)")


if __name__ == "__main__":
    main()
