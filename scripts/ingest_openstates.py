"""
TERRAIN Agent E — State P2 Alignment via DIME CFscores + Open States
=====================================================================
Approach:
  1. Fetch current state legislators from Open States API (roster only).
  2. Match each legislator to their most recent DIME CFscore record.
  3. Inverse-normalize CFscore → pro-labor signal [0,1].
  4. Aggregate to county level via state averaging (no state-leg district
     crosswalk available; congressional district crosswalk can't be used).

CFscore normalization:
  - CFscore < 0 = more progressive/pro-labor; > 0 = more conservative
  - inverse_cfscore = clip((2 - cfscore) / 4, 0, 1)
  - Maps: cfscore=-2 → 1.0, cfscore=0 → 0.5, cfscore=+2 → 0.0

Output files:
  data/processed/state_key_vote_scores.csv  — legislator-level scores
  data/processed/state_p2_county_alignment.csv — county-level aggregation

Run modes:
  python ingest_openstates.py --match-report   fetch + match + print stats (no county output)
  python ingest_openstates.py --full-run       also write county alignment CSV
"""

import csv
import json
import logging
import sys
import time
import re
from collections import defaultdict
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


def _find_file_up(filename, subpath=""):
    """Walk up from REPO_ROOT to find a file; handles git worktrees."""
    candidate = REPO_ROOT
    for _ in range(6):
        target = (candidate / subpath / filename) if subpath else (candidate / filename)
        if target.exists():
            return target
        candidate = candidate.parent
    return REPO_ROOT / subpath / filename  # fallback


ENV_FILE = _find_file_up(".env")
DATA_DIR = _find_file_up("processed", "data").parent / "processed"
RAW_DIR = _find_file_up("dime_recipients_1979_2024.csv", "data/raw").parent
CONFIG_DIR = REPO_ROOT / "config"

BASE_URL = "https://v3.openstates.org"

ALL_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]

STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "12": "FL", "13": "GA",
    "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA",
    "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO",
    "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ",
    "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC",
    "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT",
    "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY",
}

# CFscore clipping bounds for normalization
CFSCORE_MIN = -2.0
CFSCORE_MAX = 2.0

# Party imputation values for legislators with no DIME match
# Applied when match_type = 'unmatched'. Documented in STATUS_V2.md.
PARTY_IMPUTE = {
    "D": 0.75,
    "R": 0.20,
    "I": 0.50,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_api_key():
    if not ENV_FILE.exists():
        raise RuntimeError(f".env not found at {ENV_FILE}")
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("OPENSTATES_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("OPENSTATES_API_KEY not in .env")


def api_get(path, params, api_key, retries=4, pause=7.0):
    """GET from Open States API; 7s pause keeps us under 10 req/min."""
    url = f"{BASE_URL}{path}"
    headers = {"X-API-KEY": api_key}
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 15))
                log.warning("Rate limited — sleeping %ds", wait)
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            time.sleep(pause)
            return resp.json()
        except requests.RequestException as exc:
            log.warning("Attempt %d failed: %s", attempt + 1, exc)
            time.sleep(3 * (attempt + 1))
    log.error("All retries failed: %s %s", path, params)
    return None


def normalize_party(party_code):
    """DIME: 100=Dem, 200=Rep, 328=NPA/Ind. Open States: 'Democratic','Republican'."""
    try:
        code = int(party_code)
        if code == 100:
            return "D"
        if code == 200:
            return "R"
    except (ValueError, TypeError):
        p = str(party_code).lower()
        if "democrat" in p:
            return "D"
        if "republican" in p:
            return "R"
    return "I"


def normalize_os_party(party_str):
    p = party_str.lower()
    if "democrat" in p:
        return "D"
    if "republican" in p:
        return "R"
    return "I"


def inverse_cfscore(cfscore_val):
    """Map CFscore to [0,1] pro-labor signal. Lower CFscore → higher score."""
    clipped = max(CFSCORE_MIN, min(CFSCORE_MAX, cfscore_val))
    return round((CFSCORE_MAX - clipped) / (CFSCORE_MAX - CFSCORE_MIN), 4)


# ---------------------------------------------------------------------------
# Name normalization for matching
# ---------------------------------------------------------------------------

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "esq", "phd", "md"}


def extract_last_name(full_name):
    """
    Extract normalized last name from Open States full name.
    Input: 'Jane Marie Smith Jr.' → 'smith'
    Strips suffixes and punctuation, lowercases.
    """
    parts = full_name.lower().split()
    # Remove trailing suffixes
    while parts and re.sub(r"[^a-z]", "", parts[-1]) in _SUFFIXES:
        parts.pop()
    if not parts:
        return ""
    return re.sub(r"[^a-z\-]", "", parts[-1])


def extract_first_initial(full_name):
    """Return lowercase first initial from Open States name."""
    parts = full_name.lower().split()
    if parts:
        return parts[0][0] if parts[0] else ""
    return ""


def normalize_dime_lname(lname):
    """Normalize DIME lname field for matching."""
    return re.sub(r"[^a-z\-]", "", lname.lower().strip())


# ---------------------------------------------------------------------------
# Step 1 — Load DIME into lookup
# ---------------------------------------------------------------------------

def load_dime_lookup():
    """
    Load DIME state legislative records (cycles 2018+) into a lookup dict.

    Structure:
      lookup[(lname, state, chamber)] = [
          {'cycle': int, 'cfscore': float, 'party': str, 'fname': str},
          ...
      ]
    Records are stored newest-first within each key.
    """
    dime_path = RAW_DIR / "dime_recipients_1979_2024.csv"
    if not dime_path.exists():
        raise RuntimeError(f"DIME file not found at {dime_path}")

    lookup = defaultdict(list)
    total = 0
    skipped_no_score = 0

    with open(dime_path, encoding="latin-1") as f:
        reader = csv.DictReader(f)
        for row in reader:
            seat = row.get("seat", "")
            cycle_str = row.get("cycle", "")
            cfscore_str = row.get("recipient.cfscore", "")

            if "state:upper" not in seat and "state:lower" not in seat:
                continue
            try:
                cycle = int(cycle_str)
            except ValueError:
                continue
            if cycle < 2018:
                continue
            if not cfscore_str or cfscore_str.strip() in ("", "NA", "N/A"):
                skipped_no_score += 1
                continue
            try:
                cfscore = float(cfscore_str)
            except ValueError:
                skipped_no_score += 1
                continue

            if "state:upper" in seat:
                # Nebraska unicameral: DIME uses state:upper, Open States uses 'legislature'
                chamber = "legislature" if state == "NE" else "upper"
            else:
                chamber = "lower"
            lname = normalize_dime_lname(row.get("lname", ""))
            state = row.get("state", "").upper()
            fname = row.get("fname", "").lower().strip()
            party = normalize_party(row.get("party", ""))

            if not lname or not state:
                continue

            lookup[(lname, state, chamber)].append({
                "cycle": cycle,
                "cfscore": cfscore,
                "party": party,
                "fname": fname,
            })
            total += 1

    # Sort each entry newest-first
    for key in lookup:
        lookup[key].sort(key=lambda r: r["cycle"], reverse=True)

    log.info(
        "DIME loaded: %d records (2018+) across %d unique (lname,state,chamber) keys | %d skipped (no cfscore)",
        total, len(lookup), skipped_no_score,
    )
    return dict(lookup)


# ---------------------------------------------------------------------------
# Step 2 — Fetch Open States legislators
# ---------------------------------------------------------------------------

def fetch_legislators(api_key):
    """Return list of all current state legislators across all 50 states."""
    all_legislators = []
    for state in ALL_STATES:
        page = 1
        state_count = 0
        while True:
            data = api_get(
                "/people",
                {"jurisdiction": state.lower(), "per_page": 50, "page": page},
                api_key,
            )
            if not data:
                break
            results = data.get("results", [])
            if not results:
                break
            for person in results:
                role = person.get("current_role") or {}
                all_legislators.append({
                    "openstates_id": person.get("id", ""),
                    "name": person.get("name", ""),
                    "party": normalize_os_party(person.get("party", "")),
                    "state": state,
                    "chamber": role.get("org_classification", ""),  # 'upper' or 'lower'
                    "district": str(role.get("district", "") or ""),
                })
                state_count += 1
            pagination = data.get("pagination", {})
            if page >= pagination.get("max_page", 1):
                break
            page += 1
        log.info("  %s: %d legislators (running total: %d)", state, state_count, len(all_legislators))
    return all_legislators


# ---------------------------------------------------------------------------
# Step 3 — Match legislators to DIME
# ---------------------------------------------------------------------------

def match_to_dime(legislators, dime_lookup):
    """
    For each Open States legislator, find their best DIME CFscore match.

    Match priority:
      1. Exact lname + state + chamber + first-initial agreement (most recent cycle)
      2. Exact lname + state + chamber (most recent cycle, ignore first name)
      3. No match → cfscore = None

    Returns list of dicts with all legislator fields plus cfscore columns.
    """
    matched = 0
    matched_with_initial = 0
    unmatched = 0
    results = []

    for leg in legislators:
        lname = extract_last_name(leg["name"])
        first_initial = extract_first_initial(leg["name"])
        state = leg["state"]
        chamber = leg["chamber"]  # 'upper' or 'lower'

        if not lname:
            results.append({**leg, "cfscore": None, "inverse_cfscore": None,
                             "dime_cycle": None, "match_type": "no_lname"})
            unmatched += 1
            continue

        key = (lname, state, chamber)
        candidates = dime_lookup.get(key, [])

        best = None
        if candidates:
            # Try first-initial agreement on most recent cycle
            for cand in candidates:  # already newest-first
                dime_first = cand["fname"][:1] if cand["fname"] else ""
                if not first_initial or not dime_first or dime_first == first_initial:
                    best = cand
                    matched_with_initial += 1
                    break
            # Fall back to any match if no initial agreement
            if best is None:
                best = candidates[0]

        if best:
            cfs = best["cfscore"]
            results.append({
                **leg,
                "cfscore": cfs,
                "inverse_cfscore": inverse_cfscore(cfs),
                "dime_cycle": best["cycle"],
                "match_type": "matched",
            })
            matched += 1
        else:
            # Party imputation: no DIME record found
            party = leg.get("party", "I")
            imputed = PARTY_IMPUTE.get(party, PARTY_IMPUTE["I"])
            results.append({
                **leg,
                "cfscore": None,
                "inverse_cfscore": imputed,
                "dime_cycle": None,
                "match_type": "party_imputed",
            })
            unmatched += 1

    log.info(
        "Match results: %d matched (%.1f%%) | %d unmatched | of matched, %d used first-initial",
        matched, 100 * matched / len(legislators) if legislators else 0,
        unmatched, matched_with_initial,
    )
    return results, matched, unmatched


# ---------------------------------------------------------------------------
# Match report
# ---------------------------------------------------------------------------

def print_match_report(scored, matched, unmatched):
    total = len(scored)
    log.info("=== MATCH REPORT ===")
    log.info("Total Open States legislators: %d", total)
    log.info("Matched to DIME:   %d (%.1f%%)", matched, 100 * matched / total if total else 0)
    log.info("Unmatched:         %d (%.1f%%)", unmatched, 100 * unmatched / total if total else 0)

    # By state
    log.info("--- Match rate by state (lowest first) ---")
    by_state = defaultdict(lambda: {"matched": 0, "total": 0})
    for r in scored:
        st = r["state"]
        by_state[st]["total"] += 1
        if r["match_type"] == "matched":
            by_state[st]["matched"] += 1

    state_rates = sorted(
        [(st, v["matched"], v["total"], 100 * v["matched"] / v["total"]) for st, v in by_state.items()],
        key=lambda x: x[3],
    )
    for st, m, t, pct in state_rates:
        log.info("  %s: %d/%d (%.0f%%)", st, m, t, pct)

    # Score distribution for matched records
    inv_scores = [r["inverse_cfscore"] for r in scored if r["inverse_cfscore"] is not None]
    if inv_scores:
        inv_scores.sort()
        n = len(inv_scores)
        log.info("--- inverse_cfscore distribution (matched legislators) ---")
        log.info("  min=%.3f  p25=%.3f  median=%.3f  p75=%.3f  max=%.3f",
                 inv_scores[0], inv_scores[n//4], inv_scores[n//2],
                 inv_scores[3*n//4], inv_scores[-1])

    # State-level check: WI vs AL
    wi = [r["inverse_cfscore"] for r in scored if r["state"] == "WI" and r["inverse_cfscore"] is not None]
    al = [r["inverse_cfscore"] for r in scored if r["state"] == "AL" and r["inverse_cfscore"] is not None]
    if wi:
        log.info("WI avg inverse_cfscore=%.3f (n=%d, expect higher)", sum(wi)/len(wi), len(wi))
    if al:
        log.info("AL avg inverse_cfscore=%.3f (n=%d, expect lower)", sum(al)/len(al), len(al))


# ---------------------------------------------------------------------------
# Step 4 — Write legislator scores CSV
# ---------------------------------------------------------------------------

def write_legislator_scores(scored):
    out = DATA_DIR / "state_key_vote_scores.csv"
    fieldnames = [
        "openstates_id", "name", "state", "party", "chamber", "district",
        "cfscore", "inverse_cfscore", "dime_cycle", "match_type",
        # Legacy columns (null in this version — floor votes deferred)
        "votes_cast", "pro_labor_votes", "key_vote_score", "bills_found",
    ]
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in scored:
            out_row = {k: row.get(k, "") for k in fieldnames}
            # key_vote_score = inverse_cfscore (primary signal in this version)
            out_row["key_vote_score"] = row.get("inverse_cfscore", "")
            out_row["votes_cast"] = ""
            out_row["pro_labor_votes"] = ""
            out_row["bills_found"] = ""
            writer.writerow(out_row)
    log.info("Wrote %s (%d rows)", out, len(scored))


# ---------------------------------------------------------------------------
# Step 5 — County aggregation
# ---------------------------------------------------------------------------

def load_county_list():
    """Load all county FIPS codes from the district-county crosswalk."""
    crosswalk = DATA_DIR / "district_county_crosswalk.csv"
    counties = {}
    with open(crosswalk) as f:
        reader = csv.DictReader(f)
        for row in reader:
            fips = row["county_fips"]
            state_fips = fips[:2]
            state_abbr = STATE_FIPS.get(state_fips, "")
            if fips not in counties:
                counties[fips] = {"fips": fips, "state": state_abbr}
    return counties


def aggregate_to_county(scored, counties):
    """
    State-level average of inverse_cfscore → county.
    coverage_type = 'cfscore_only' (floor vote supplement deferred to v2).
    """
    state_scores = defaultdict(list)
    state_leg_counts = defaultdict(int)

    for row in scored:
        state_leg_counts[row["state"]] += 1
        if row["inverse_cfscore"] is not None:
            state_scores[row["state"]].append(row["inverse_cfscore"])

    state_avg = {
        st: round(sum(scores) / len(scores), 4)
        for st, scores in state_scores.items() if scores
    }

    county_rows = []
    # Track per-state imputation share to set coverage_type
    state_imputed_counts = defaultdict(int)
    for row in scored:
        if row.get("match_type") == "party_imputed":
            state_imputed_counts[row["state"]] += 1

    for fips, county in counties.items():
        state = county["state"]
        if not state:
            continue
        if state in state_avg:
            p2_score = state_avg[state]
            leg_count = state_leg_counts[state]
            imputed = state_imputed_counts.get(state, 0)
            matched_count = leg_count - imputed
            # Label coverage by how much of the average is DIME-matched vs imputed
            if matched_count == 0:
                cov = "party_imputed"
            elif imputed == 0:
                cov = "cfscore_only"
            else:
                cov = "cfscore_plus_imputed"
        else:
            p2_score = None
            cov = "no_data"
            leg_count = 0

        county_rows.append({
            "fips": fips,
            "county_name": "",
            "state": state,
            "state_p2_score": p2_score,
            "state_legislator_count": leg_count,
            "state_bills_found": 0,
            "coverage_type": cov,
        })

    return county_rows


def write_county_alignment(county_rows):
    out = DATA_DIR / "state_p2_county_alignment.csv"
    fieldnames = [
        "fips", "county_name", "state",
        "state_p2_score", "state_legislator_count",
        "state_bills_found", "coverage_type",
    ]
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in county_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    log.info("Wrote %s (%d rows)", out, len(county_rows))


# ---------------------------------------------------------------------------
# Spot-check validation
# ---------------------------------------------------------------------------

SPOT_CHECK_FIPS = {
    "42027": "Centre County PA",
    "55045": "Green County WI",
    "01073": "Jefferson County AL",
    "17031": "Cook County IL",
    "04013": "Maricopa County AZ",
}


def spot_check(county_rows):
    by_fips = {r["fips"]: r for r in county_rows}
    log.info("=== SPOT CHECKS ===")
    for fips, label in SPOT_CHECK_FIPS.items():
        row = by_fips.get(fips)
        if row:
            log.info("  %s (%s): state_p2=%.3f coverage=%s",
                     label, fips, row["state_p2_score"] or 0, row["coverage_type"])
        else:
            log.warning("  %s (%s): NOT FOUND", label, fips)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--match-report"

    api_key = load_api_key()
    log.info("API key loaded. Mode: %s", mode)

    # --- Load DIME ---
    log.info("=== Loading DIME CFscores ===")
    dime_lookup = load_dime_lookup()

    # --- Fetch legislators ---
    log.info("=== Fetching Open States legislators (7s/request) ===")
    legislators = fetch_legislators(api_key)
    log.info("Total legislators fetched: %d", len(legislators))

    # --- Match ---
    log.info("=== Matching to DIME ===")
    scored, matched, unmatched = match_to_dime(legislators, dime_lookup)

    # --- Report ---
    print_match_report(scored, matched, unmatched)

    if mode == "--match-report":
        log.info("Match report complete. Run with --full-run to write output files.")
        # Write legislator scores (no county file yet)
        write_legislator_scores(scored)
        return

    # --- Full run: county aggregation ---
    log.info("=== County aggregation ===")
    counties = load_county_list()
    county_rows = aggregate_to_county(scored, counties)
    log.info("County rows: %d", len(county_rows))

    write_legislator_scores(scored)
    write_county_alignment(county_rows)
    spot_check(county_rows)

    log.info("=== DONE ===")


if __name__ == "__main__":
    main()
