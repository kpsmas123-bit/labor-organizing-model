"""
Terrain v2.0 — State P2 Refresh Script

Monthly refresh of state legislative P2 alignment scores.
Designed to run in GitHub Actions or locally.

Usage:
  python scripts/refresh_state_p2.py           # full run
  python scripts/refresh_state_p2.py --dry-run # fetch only, no write
  python scripts/refresh_state_p2.py --states WA WV WI WY  # specific states only

Reads:
  data/raw/dime_recipients_1979_2024.csv
  OPENSTATES_API_KEY from environment

Writes:
  data/processed/state_p2_county_alignment.csv
  logs/state_p2_refresh.log
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import requests

# --- Config ---
OPENSTATES_API_KEY = os.environ.get("OPENSTATES_API_KEY")
BASE_URL = "https://v3.openstates.org"
RATE_LIMIT_DELAY = 7  # seconds between requests (free tier: 10/min)
DIME_CYCLES = [2018, 2020, 2022]  # most recent reliable cycles
PARTY_IMPUTATION = {"Republican": 0.20, "Democrat": 0.75, "Independent": 0.50}
CFSCORE_CLIP_MIN, CFSCORE_CLIP_MAX = -2.0, 2.0

# Nebraska unicameral maps to state:upper in DIME
NE_CHAMBER_MAP = {"legislature": "upper"}
AT_LARGE_STATES = {"AK", "DE", "ND", "SD", "VT", "WY"}

def normalize_cfscore(score, clip_min=-2.0, clip_max=2.0):
    """Convert raw CFscore to inverse pro-labor signal (0-1)."""
    clipped = max(clip_min, min(clip_max, score))
    return round((clip_max - clipped) / (clip_max - clip_min), 4)

def load_dime(dime_path, cycles):
    """Load DIME CFscores for state legislators, filtered to recent cycles."""
    lookup = {}  # (name_normalized, state, chamber_type, cycle) → cfscore
    with open(dime_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            seat = row.get("seat", "")
            if not seat.startswith("state:"):
                continue
            cycle = int(row.get("cycle", 0))
            if cycle not in cycles:
                continue
            name = row.get("name", "").strip().upper()
            state = row.get("state", "").strip().upper()
            chamber = seat.split(":")[1]  # "upper" or "lower"
            try:
                cfscore = float(row.get("recipient.cfscore", ""))
            except (ValueError, TypeError):
                continue
            key = (name, state, chamber, cycle)
            lookup[key] = cfscore
    return lookup

def fetch_state_legislators(state, session):
    """Fetch all current legislators for a state from Open States."""
    legislators = []
    page = 1
    while True:
        resp = session.get(
            f"{BASE_URL}/people",
            params={"state": state.lower(), "per_page": 50, "page": page},
        )
        if resp.status_code == 429:
            logging.warning(f"{state}: rate limited, sleeping 65s")
            time.sleep(65)
            continue
        if resp.status_code == 400:
            logging.error(f"{state}: 400 error — skipping (likely per_page too large)")
            break
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        legislators.extend(results)
        if not data.get("pagination", {}).get("next_page"):
            break
        page += 1
        time.sleep(RATE_LIMIT_DELAY)
    return legislators

def match_legislator(leg, dime_lookup, state):
    """Match a legislator to DIME CFscore. Returns (inverse_cfscore, coverage_type)."""
    name = leg.get("name", "").upper().strip()
    role = leg.get("current_role", {}) or {}
    chamber = role.get("chamber", "").lower()

    # Nebraska special case
    if state == "NE":
        chamber = NE_CHAMBER_MAP.get(chamber, chamber)

    # Map chamber to DIME format
    chamber_map = {"upper": "upper", "lower": "lower", "senate": "upper", "house": "lower"}
    dime_chamber = chamber_map.get(chamber, chamber)

    # Try matching across recent cycles (most recent first)
    for cycle in sorted(DIME_CYCLES, reverse=True):
        key = (name, state.upper(), dime_chamber, cycle)
        if key in dime_lookup:
            raw = dime_lookup[key]
            return normalize_cfscore(raw), "cfscore_matched"

    # Party imputation fallback
    party = leg.get("party", "")
    if "Republican" in party or "GOP" in party:
        return PARTY_IMPUTATION["Republican"], "party_imputed"
    elif "Democrat" in party:
        return PARTY_IMPUTATION["Democrat"], "party_imputed"
    else:
        return PARTY_IMPUTATION["Independent"], "party_imputed"

def aggregate_to_counties(state_scores, crosswalk_path):
    """Average state legislator scores to counties using state-level averaging."""
    county_scores = {}
    state_to_counties = defaultdict(list)

    with open("data/county_scores_v2_test.json") as f:
        data = json.load(f)
        counties = data.get("counties", data) if isinstance(data, dict) else data

    for county in counties:
        fips = str(county.get("fips", "")).zfill(5)
        state = county.get("state", "")
        county_scores[fips] = {
            "county_name": county.get("county_name", ""),
            "state": state,
        }
        state_to_counties[state].append(fips)

    # Compute state-level average scores
    state_averages = {}
    for state, scores_list in state_scores.items():
        if scores_list:
            avg = sum(s[0] for s in scores_list) / len(scores_list)
            n_matched = sum(1 for s in scores_list if s[1] == "cfscore_matched")
            n_imputed = sum(1 for s in scores_list if s[1] == "party_imputed")
            coverage = "cfscore_plus_imputed" if n_matched > 0 else "party_imputed_only"
            state_averages[state] = (round(avg, 4), coverage, len(scores_list), n_matched)

    # Map to counties
    output = []
    for fips, info in county_scores.items():
        state = info["state"]
        if state in state_averages:
            score, coverage, n_leg, n_matched = state_averages[state]
        else:
            score, coverage, n_leg, n_matched = None, "no_data", 0, 0
        output.append({
            "fips": fips,
            "county_name": info["county_name"],
            "state": state,
            "state_p2_score": score,
            "coverage_type": coverage,
            "legislator_count": n_leg,
            "matched_count": n_matched,
            "generated": datetime.now().isoformat(),
        })
    return output

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--states", nargs="+", help="Specific states to fetch (e.g. WA WI WV WY)")
    args = parser.parse_args()

    # Setup logging
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "state_p2_refresh.log"),
        ],
    )

    if not OPENSTATES_API_KEY:
        logging.error("OPENSTATES_API_KEY not set in environment")
        sys.exit(1)

    # Load DIME
    dime_path = Path("data/raw/dime_recipients_1979_2024.csv")
    if not dime_path.exists():
        logging.error(f"DIME file not found at {dime_path}")
        sys.exit(1)
    logging.info("Loading DIME CFscores...")
    dime_lookup = load_dime(dime_path, DIME_CYCLES)
    logging.info(f"DIME loaded: {len(dime_lookup):,} state legislator records")

    # Setup API session
    session = requests.Session()
    session.headers.update({"X-API-KEY": OPENSTATES_API_KEY})

    # States to process
    all_states = [
        "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
        "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
        "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
        "TX","UT","VT","VA","WA","WV","WI","WY"
    ]
    states = args.states if args.states else all_states

    # Fetch and match
    state_scores = {}
    for state in states:
        logging.info(f"Fetching {state}...")
        try:
            legislators = fetch_state_legislators(state, session)
            scores = []
            for leg in legislators:
                score, coverage = match_legislator(leg, dime_lookup, state)
                scores.append((score, coverage))
            n_matched = sum(1 for _, c in scores if c == "cfscore_matched")
            logging.info(f"{state}: {len(legislators)} legislators, {n_matched} DIME matched ({n_matched/len(legislators)*100:.0f}%)")
            state_scores[state] = scores
        except Exception as e:
            logging.error(f"{state}: failed — {e}")
            state_scores[state] = []
        time.sleep(RATE_LIMIT_DELAY)

    # Aggregate to counties
    logging.info("Aggregating to counties...")
    output = aggregate_to_counties(state_scores, None)

    if args.dry_run:
        logging.info(f"DRY RUN complete — {len(output)} counties processed, no file written")
        return

    # Write output
    out_path = Path("data/processed/state_p2_county_alignment.csv")
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "fips","county_name","state","state_p2_score",
            "coverage_type","legislator_count","matched_count","generated"
        ])
        writer.writeheader()
        writer.writerows(output)

    n_covered = sum(1 for r in output if r["state_p2_score"] is not None)
    logging.info(f"Written: {out_path} — {len(output)} counties, {n_covered} with state P2 data")

if __name__ == "__main__":
    main()
