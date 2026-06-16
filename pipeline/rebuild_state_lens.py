"""
State-lens rebuild v2 (Agent 1, Phase 2 RE-RUN).

Supersedes the earlier `state-lens-rebuild` dress rehearsal: that run used a
LINEAR-from-0 competitiveness band (comp = max(0,(BAND-|margin|)/BAND)) on
pre-backfill data. This v2 run uses the FINALIZED plateau-fade competitiveness
function and the now-merged 5-state overlay (VA/NJ/MS/LA/NE).

Surgically recomputes ONLY the state-lens fields of data/county_scores.json:
  * p1_state            competitiveness x chamber-flip proximity
  * p2_state            party proxy (county-resolved, overlap-weighted Dem share)
  * quadrant_state      existing 6-tier classifier on state-lens inputs
  * state_p2_coverage   = party_proxy (or party_proxy_state_uniform fallback)
  * p1_state_data_tier  confidence of the margin, with vintage carried through
                        (e.g. "gubernatorial:2021" for stale VA rows)
  * margin_stale        carried from competitiveness file
  * state_noncomp_priority  low-P1 alignment subdivision (hostile/neutral/aligned)

National fields and SLS are NOT touched (verified 0 diffs across ALL counties).
The classifier is the EXISTING classify() from build_v2_canonical.py.

COMPETITIVENESS — plateau fade (finalized). comp(|margin|), margin = two-party %:
    |margin| <= PLATEAU_EDGE                       -> 1.0   (toss-up, full weight)
    PLATEAU_EDGE < |margin| < ZERO_EDGE            -> (ZERO_EDGE-|margin|)/(ZERO_EDGE-PLATEAU_EDGE)
    |margin| >= ZERO_EDGE                          -> 0.0
  Continuous at PLATEAU_EDGE (both pieces = 1.0). Full weight through the toss-up
  band, then linear decay to zero at the lean edge — the model does not draw
  distinctions finer than the data's reliability (vintage / proxy error) supports.

SINGLE-SOURCE CONFIG: PLATEAU_EDGE, ZERO_EDGE and p1_high_state are read from
config/thresholds.json -> "state_competitiveness". Nothing here hardcodes them.

  P1_state = 100 * chamber_flip_proximity * comp(margin)
    chamber_flip_proximity  = tipping_weights[<state>_<chamber of most-competitive seat>]
                              (1 - seats_from_flip/total_seats; near-tie -> ~1.0)
                              fallback: state-mean chamber proximity; None for DC/DE.

  P2_state = overlap-weighted Democratic share of the county's CURRENT state-leg
             representation, from data/work_stateleg/county_seat_detail.json.
             0 = all-R (hostile), 1 = all-D (aligned). Counties with no resolvable
             overlap fall back to the state-uniform legislative Dem share (flagged).

  Overlay: data/processed/state_leg_competitiveness_backfill.csv rows REPLACE base
           rows by fips (higher-confidence gubernatorial/state-returns). NO swing
           buffer or synthetic adjustment is applied to any state; stale sources
           (VA 2021) are included and flagged by vintage in p1_state_data_tier.

Run:
  python pipeline/rebuild_state_lens.py --write   (overwrite county_scores.json, backup first)
  python pipeline/rebuild_state_lens.py           (dry-run: print distribution + selectivity report)
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

COMP_PATH = ROOT / "data/processed/state_leg_competitiveness.csv"
OVERLAY_PATH = ROOT / "data/processed/state_leg_competitiveness_backfill.csv"
SEAT_DETAIL_PATH = ROOT / "data/work_stateleg/county_seat_detail.json"
CHAMBER_PATH = ROOT / "data/processed/chamber_seat_counts.json"
SCORES_PATH = ROOT / "data/county_scores.json"
THRESHOLDS_PATH = ROOT / "config/thresholds.json"

# Candidate selectivity thresholds for the decision-B report (Sam picks one).
# The brief suggested {20,30,40}, but on the finalized plateau-fade those three
# sit on a flat shoulder — all within 1.4pp of map (11.8% / 11.3% / 10.4%) — so
# they don't bracket a sensible range. Widened to {30,60,90} to span from a
# loose state lens (~11% of map) to national-tight (~2%), where Tier1/Tier3
# selectivity actually moves. The full >=threshold curve is also printed.
CANDIDATE_P1_HIGH = [30, 60, 90]
CURVE_THRESHOLDS = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90]


# --------------------------------------------------------------- inputs

def load_competitiveness():
    """fips -> row. Overlay rows (if present) REPLACE base rows by fips."""
    base = {r["fips"]: r for r in csv.DictReader(open(COMP_PATH))}
    overlay_found = False
    overlay_fips = []
    if OVERLAY_PATH.exists():
        overlay_found = True
        for r in csv.DictReader(open(OVERLAY_PATH)):
            base[r["fips"]] = r  # higher-confidence row wins
            overlay_fips.append(r["fips"])
    return base, overlay_found, overlay_fips


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

def comp_signal(margin, plateau_edge, zero_edge):
    """
    Plateau-fade competitiveness in [0, 1]. margin is a two-party margin (pp).
      |margin| <= plateau_edge          -> 1.0
      plateau_edge < |margin| < zero_edge -> linear decay to 0 at zero_edge
      |margin| >= zero_edge             -> 0.0
    Continuous at plateau_edge (the decay piece evaluates to 1.0 there).
    """
    if margin is None:
        return 0.0
    a = abs(margin)
    if a <= plateau_edge:
        return 1.0
    if a >= zero_edge:
        return 0.0
    return (zero_edge - a) / (zero_edge - plateau_edge)


def proximity_for(row, tw, state_mean):
    """Chamber-flip proximity for a county. None when the state has no chamber data."""
    bs = best_seat_chamber(row.get("source", ""))
    if bs:
        key = f"{bs[0]}_{bs[1]}"
        if key in tw:
            return tw[key]
    return state_mean.get(row["state"])  # presidential-tier / unnamed-seat fallback


def score_p1_state(row, tw, state_mean, plateau_edge, zero_edge):
    try:
        margin = float(row["margin"])
    except (TypeError, ValueError):
        margin = None
    prox = proximity_for(row, tw, state_mean)
    if prox is None or margin is None:
        return 0.0, prox  # DC/DE (no chamber data) or no margin -> floor
    return round(100.0 * prox * comp_signal(margin, plateau_edge, zero_edge), 2), prox


def data_tier_with_vintage(row):
    """
    Carry the margin's confidence tier AND its vintage through to p1_state_data_tier.
    Stale sources (e.g. VA 2021 gubernatorial) are flagged here by vintage; no
    numeric/swing adjustment is applied. Format: "<tier>:<vintage>" when a vintage
    is present, else just "<tier>".
    """
    tier = row.get("p1_data_tier", "missing")
    vintage = (row.get("vintage") or "").strip()
    return f"{tier}:{vintage}" if vintage else tier


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

    comp, overlay_found, overlay_fips = load_competitiveness()
    seat_detail = json.load(open(SEAT_DETAIL_PATH))
    chamber_json = json.load(open(CHAMBER_PATH))
    tw, state_mean, state_dem_share = build_chamber_proximity(chamber_json)
    thresholds = json.load(open(THRESHOLDS_PATH))
    scores = json.load(open(SCORES_PATH))

    # ---- SINGLE-SOURCE CONFIG: read every band parameter from thresholds.json ----
    sc = thresholds["state_competitiveness"]
    PLATEAU_EDGE = sc["plateau_edge"]
    ZERO_EDGE = sc["zero_edge"]
    P1_HIGH_STATE = sc["p1_high_state"]

    # continuity check at the plateau edge (both pieces must equal 1.0)
    eps = 1e-9
    left = comp_signal(PLATEAU_EDGE, PLATEAU_EDGE, ZERO_EDGE)
    right = comp_signal(PLATEAU_EDGE + eps, PLATEAU_EDGE, ZERO_EDGE)
    assert abs(left - 1.0) < 1e-6 and abs(right - 1.0) < 1e-3, (
        f"comp() discontinuous at PLATEAU_EDGE: left={left}, right={right}")

    q = thresholds["quadrant"]
    # State-lens thresholds: SLS + P2 identical to national; ONLY p1 differs (scale differs).
    T_state = {
        "sls_capital": q["sls_capital_high_boundary"],
        "sls_community": q["sls_community_high_boundary"],
        "p1": P1_HIGH_STATE,               # from state_competitiveness block
        "p2_hostile": q["p2_hostile_ceiling"],
        "p2_aligned": q["p2_aligned_floor"],
    }

    canon_fips = {c["fips"] for c in scores["counties"]}
    comp_not_canon = sorted(set(comp) - canon_fips)
    canon_not_comp = sorted(canon_fips - set(comp))

    # National + SLS field snapshot across ALL counties (true 0-diff verification).
    untouched_keys = ["p1_national", "p2_national", "p1_presidential", "p2_alignment",
                      "federal_p2", "quadrant_national", "quadrant",
                      "sls_capital", "sls_community"]
    before_snapshot = {c["fips"]: {k: c.get(k) for k in untouched_keys}
                       for c in scores["counties"]}

    log = {
        "version": "v2 (plateau-fade, post-backfill)",
        "plateau_edge": PLATEAU_EDGE,
        "zero_edge": ZERO_EDGE,
        "p1_high_state": P1_HIGH_STATE,
        "overlay_found": overlay_found,
        "overlay_row_count": len(overlay_fips),
        "comp_rows_not_in_canonical": comp_not_canon,
        "canonical_not_in_comp": canon_not_comp,
        "p2_fallback_state_uniform": [],
        "p2_unavailable": [],
        "p1_floor_no_chamber": [],
        "national_sls_diffs": [],
    }

    # First pass: compute the state-lens inputs (p1_state, p2_state) for every county.
    computed = []  # parallel to scores["counties"]
    st_counts = defaultdict(int)
    sub_counts = defaultdict(int)
    for c in scores["counties"]:
        fips = c["fips"]
        state_abbr = c["state"]
        row = comp.get(fips, {"state": state_abbr, "margin": None, "source": "",
                              "p1_data_tier": "missing", "margin_stale": "False",
                              "vintage": ""})

        p1_state, prox = score_p1_state(row, tw, state_mean, PLATEAU_EDGE, ZERO_EDGE)
        if prox is None:
            log["p1_floor_no_chamber"].append(fips)

        p2_state, p2_cov = score_p2_state(fips, seat_detail, state_abbr, state_dem_share)
        if p2_cov == "party_proxy_state_uniform":
            log["p2_fallback_state_uniform"].append(fips)
        elif p2_cov == "party_proxy_unavailable":
            log["p2_unavailable"].append(fips)

        quadrant_state = classify(c["sls_capital"], c["sls_community"],
                                  p1_state, p2_state, T_state)

        # subdivide the NON-competitive (low-P1) band by alignment (additive only).
        if p1_state < T_state["p1"]:
            if p2_state < q["p2_hostile_ceiling"]:
                sub = "hostile"
            elif p2_state >= q["p2_aligned_floor"]:
                sub = "aligned"
            else:
                sub = "neutral"
        else:
            sub = None  # high-P1 tiers untouched
        sub_counts[sub] += 1

        computed.append({
            "p1_state": p1_state,
            "p2_state": p2_state,
            "state_p2_coverage": p2_cov,
            "p1_state_data_tier": data_tier_with_vintage(row),
            "margin_stale": (str(row.get("margin_stale", "False")).lower() == "true"),
            "quadrant_state": quadrant_state,
            "state_noncomp_priority": sub,
        })
        st_counts[quadrant_state] += 1

    # ---- DECISION-B SELECTIVITY REPORT: re-classify at each candidate threshold ----
    n_total = len(scores["counties"])
    selectivity = []
    for cand in CANDIDATE_P1_HIGH:
        T_cand = dict(T_state, p1=cand)
        t1 = t3 = n_high = 0
        for c, comp_c in zip(scores["counties"], computed):
            p1 = comp_c["p1_state"]
            if p1 >= cand:
                n_high += 1
            quad = classify(c["sls_capital"], c["sls_community"],
                            p1, comp_c["p2_state"], T_cand)
            if quad.startswith("tier1"):
                t1 += 1
            elif quad == "tier3_electoral":
                t3 += 1
        selectivity.append({
            "p1_high_state": cand,
            "high_p1_counties": n_high,
            "pct_of_map": round(n_high / n_total * 100, 1),
            "tier1": t1,
            "tier3": t3,
        })
    log["selectivity_report"] = selectivity

    # full high-P1 curve (count + % of map) for context — selectivity is flat
    # below ~40 and only steepens above it.
    p1_vals = [comp_c["p1_state"] for comp_c in computed]
    curve = [{"threshold": t,
              "high_p1_counties": sum(1 for v in p1_vals if v >= t),
              "pct_of_map": round(sum(1 for v in p1_vals if v >= t) / n_total * 100, 1)}
             for t in CURVE_THRESHOLDS]
    log["high_p1_curve"] = curve
    log["nonzero_p1_counties"] = sum(1 for v in p1_vals if v > 0)

    # write the state-lens fields, then verify national/SLS untouched (all counties).
    for c, comp_c in zip(scores["counties"], computed):
        for k, v in comp_c.items():
            c[k] = v
        after = {k: c.get(k) for k in untouched_keys}
        if after != before_snapshot[c["fips"]]:
            log["national_sls_diffs"].append(c["fips"])

    # metadata block
    scores["_tier_counts_state"] = dict(st_counts)
    scores["_state_lens_rebuild"] = {
        "version": "v2 plateau-fade",
        "rebuilt": datetime.now(timezone.utc).isoformat(),
        "formula": "P1_state=100*chamber_flip_proximity*comp(margin); "
                   "comp: 1.0 for |m|<=plateau_edge, linear decay to 0 at zero_edge; "
                   "P2_state=overlap-weighted Dem share of current state-leg roster",
        "plateau_edge": PLATEAU_EDGE,
        "zero_edge": ZERO_EDGE,
        "p1_high_state": P1_HIGH_STATE,
        "overlay_found": overlay_found,
        "overlay_row_count": len(overlay_fips),
        "p2_fallback_count": len(log["p2_fallback_state_uniform"]),
        "noncomp_subdivision": dict(sub_counts),
        "national_sls_diffs": len(log["national_sls_diffs"]),
    }

    # --------------------------------------------------------- print
    print("== STATE-LENS REBUILD v2 (plateau-fade) ==")
    print(f"PLATEAU_EDGE={PLATEAU_EDGE}  ZERO_EDGE={ZERO_EDGE}  "
          f"p1_high_state={P1_HIGH_STATE} (config-sourced)")
    print(f"comp continuity at edge: left={left:.6f} right={right:.6f} (== 1.0 OK)")
    print(f"overlay_found: {overlay_found}  rows: {len(overlay_fips)} "
          f"-> states {sorted({comp[f]['state'] for f in overlay_fips})}")
    print(f"comp rows not in canonical (logged, not force-fit): {comp_not_canon}")
    print(f"canonical not in comp: {canon_not_comp}")
    print(f"P2 state-uniform fallbacks: {len(log['p2_fallback_state_uniform'])}")
    print(f"P2 unavailable (neutral 0.5): {log['p2_unavailable']}")
    print(f"P1 floor (no chamber data): {len(log['p1_floor_no_chamber'])} -> "
          f"{sorted({f[:2] for f in log['p1_floor_no_chamber']})}")

    print("\n-- DECISION B: selectivity at candidate p1_high_state thresholds --")
    print(f"{'p1_high_state':>14} | {'high-P1':>8} | {'% of map':>8} | "
          f"{'Tier 1':>7} | {'Tier 3':>7}")
    print("-" * 60)
    for s in selectivity:
        print(f"{s['p1_high_state']:>14} | {s['high_p1_counties']:>8} | "
              f"{s['pct_of_map']:>7}% | {s['tier1']:>7} | {s['tier3']:>7}")

    print(f"\n  (full high-P1 curve — {log['nonzero_p1_counties']} counties have nonzero P1)")
    print(f"  {'>= thr':>7} | {'high-P1':>8} | {'% of map':>8}")
    for cv in curve:
        print(f"  {cv['threshold']:>7} | {cv['high_p1_counties']:>8} | {cv['pct_of_map']:>7}%")

    print(f"\nState tier counts (at configured p1_high_state={P1_HIGH_STATE}):")
    for k in sorted(st_counts):
        print(f"  {k:<28} {st_counts[k]:>5}")
    print("\nNon-competitive (low-P1) alignment subdivision:")
    for k in sorted(sub_counts, key=lambda x: (x is None, x)):
        print(f"  {str(k):<12} {sub_counts[k]:>5}")
    print(f"\nNational + SLS field diffs across all {n_total} counties: "
          f"{len(log['national_sls_diffs'])} (expect 0)")

    if args.write:
        if log["national_sls_diffs"]:
            raise SystemExit(f"ABORT: national/SLS fields changed for "
                             f"{len(log['national_sls_diffs'])} counties — refusing to write.")
        archive = ROOT / "data" / "archive"
        archive.mkdir(exist_ok=True)
        backup = archive / "county_scores_pre_state_lens_rebuild.json"
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
