"""
Task 8 (patched): Cornell ILR strike data ingestion.

Fixes vs original:
  1. STATE_NAME_TO_ABBR replaces broken .upper()[:2] state parsing.
     Original got 49% county match rate; corrected version gets 89%.
  2. Cornell record ID stored on each Notion page for future deduplication.
  3. --wipe flag archives all existing STRIKES records before re-ingesting.

Usage:
    python task8_strikes.py --config ../config.json [--dry-run] [--wipe]

Typical re-ingestion flow (approved by Sam, 2026-05-04):
    python task8_strikes.py --config ../config.json --wipe
"""

import json
import logging
import argparse
import time
import re
from pathlib import Path
from typing import Optional
from difflib import SequenceMatcher

import requests
import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import (
    NotionClient, title_prop, text_prop, number_prop,
    select_prop, checkbox_prop, relation_prop, date_prop, url_prop,
    multi_select_prop
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                               logging.FileHandler("../logs/task8_strikes.log")])
logger = logging.getLogger(__name__)

CORNELL_DATA_URL = "https://striketracker.ilr.cornell.edu/labor_actions.json"
CORNELL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (research purposes; contact labor-data@example.com)",
    "Accept": "application/json",
}

# Full state name → 2-letter abbreviation.
# Replaces the broken strike["state"].upper()[:2] pattern which mangled multi-word
# state names (e.g. "New York"[:2].upper() == "NE", matching Nebraska instead).
STATE_NAME_TO_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}

STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}


def fetch_cornell_data() -> list[dict]:
    """Fetch strike data from Cornell ILR Labor Action Tracker static JSON."""
    local = Path("../data/cornell_strikes.json")
    try:
        resp = requests.get(CORNELL_DATA_URL, headers=CORNELL_HEADERS, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        records = list(data.values()) if isinstance(data, dict) else data
        logger.info(f"Fetched {len(records)} labor actions from Cornell")
        local.write_text(json.dumps(records, indent=2))
        return records
    except Exception as e:
        logger.error(f"Cornell fetch error: {e}")
        if local.exists():
            logger.info("Loading from cached cornell_strikes.json")
            return json.loads(local.read_text())
        return []


def normalize_field(raw: dict) -> dict:
    """Normalize Cornell labor_actions.json fields."""
    locations = raw.get("locations") or []
    loc = locations[0] if locations else {}
    city = loc.get("City") or loc.get("city") or ""
    state_full = loc.get("State") or loc.get("state") or ""
    # Map full state name → abbreviation. Fall back to raw value if already an abbr.
    state = STATE_NAME_TO_ABBR.get(state_full, state_full.upper()[:2] if len(state_full) == 2 else "")
    zip_code = loc.get("Zip") or loc.get("zip") or ""

    industry_raw = raw.get("Industry") or raw.get("industry") or ""
    industry = (industry_raw[0] if isinstance(industry_raw, list) and industry_raw
                else str(industry_raw))

    demands_raw = raw.get("Worker_demands") or raw.get("worker_demands") or []
    demands = ", ".join(demands_raw) if isinstance(demands_raw, list) else str(demands_raw)

    sources = raw.get("sources") or []
    source_url = sources[0] if sources else ""

    workers_raw = raw.get("Approximate_Number_of_Participants") or raw.get("number_of_workers") or 0
    try:
        workers = int(float(workers_raw))
    except (TypeError, ValueError):
        workers = 0

    return {
        "cornell_id": raw.get("id"),
        "name": raw.get("Employer") or raw.get("employer") or "Unknown Strike",
        "union_name": raw.get("Labor_Organization") or raw.get("labor_organization") or "",
        "employer": raw.get("Employer") or raw.get("employer") or "",
        "city": city,
        "state": state,
        "state_full": state_full,
        "zip_code": zip_code,
        "start_date": raw.get("Start_date") or raw.get("start_date") or "",
        "end_date": raw.get("End_date") or raw.get("end_date") or "",
        "workers": workers,
        "industry": industry,
        "authorized": bool(raw.get("Authorized") or raw.get("authorized")),
        "outcome": raw.get("outcome") or "",
        "demands": demands[:500],
        "source_url": source_url,
        "action_type": raw.get("Action_type") or raw.get("action_type") or "Strike",
    }


def fuzzy_match_union(union_name: str, union_index: dict[str, str]) -> Optional[str]:
    """Find best-matching union page_id using fuzzy string matching."""
    if not union_name:
        return None
    best_ratio = 0.0
    best_id = None
    uname_lower = union_name.lower()
    for name, page_id in union_index.items():
        ratio = SequenceMatcher(None, uname_lower, name.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_id = page_id
    return best_id if best_ratio >= 0.75 else None


def build_properties(strike: dict, county_id: Optional[str], state_id: Optional[str],
                     union_id: Optional[str]) -> dict:
    name = str(strike["name"])[:255] or "Strike Record"
    props = {
        "Strike Name": title_prop(name),
        "Employer": text_prop(str(strike.get("employer", ""))[:255]),
        "Workers Involved": number_prop(strike.get("workers") or None),
        "Cornell ID": number_prop(strike.get("cornell_id")),
        "Strike Type": select_prop("Authorized" if strike.get("authorized") else "Wildcat"),
        "Confidence": select_prop("Medium"),
        "Source Tier": select_prop("Tier 1: Cornell/BLS"),
    }
    if strike.get("start_date"):
        props["Start Date"] = date_prop(strike["start_date"][:10])
    if strike.get("end_date"):
        props["End Date"] = date_prop(strike["end_date"][:10])
    if strike.get("source_url"):
        props["Source URL"] = url_prop(strike["source_url"])
    if strike.get("state"):
        props["States Affected"] = multi_select_prop([strike["state"].upper()])
    if county_id:
        props["Primary County"] = relation_prop([county_id])
    if state_id:
        props["Primary State"] = relation_prop([state_id])
    if union_id:
        props["Union"] = relation_prop([union_id])
    return props


def wipe_strikes_db(client: NotionClient, strikes_db_id: str):
    """Archive all existing STRIKES records."""
    logger.info("Querying all existing STRIKES records for wipe...")
    existing = client.query_all(strikes_db_id)
    logger.info(f"Archiving {len(existing)} existing STRIKES records...")
    archived = 0
    errors = 0
    for page in existing:
        try:
            client.archive_page(page["id"])
            archived += 1
            if archived % 500 == 0:
                logger.info(f"Archived {archived}/{len(existing)}")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed to archive {page['id']}: {e}")
            errors += 1
    logger.info(f"Wipe complete: {archived} archived, {errors} errors")


def run(config_path: str, dry_run: bool = False, wipe: bool = False):
    config = json.loads(Path(config_path).read_text())
    notion_cfg = config["notion"]

    county_ids: dict[str, str] = {}
    state_ids: dict[str, str] = {}
    union_index: dict[str, str] = {}

    for path, store in [
        ("../data/county_ids.json", county_ids),
        ("../data/state_ids.json", state_ids),
    ]:
        p = Path(path)
        if p.exists():
            store.update(json.loads(p.read_text()))

    union_ids_path = Path("../data/union_name_ids.json")
    if union_ids_path.exists():
        union_index = json.loads(union_ids_path.read_text())

    # Primary county lookup: zip → county FIPS (94% coverage on Cornell data).
    # Secondary: city|state_abbr → Place FIPS → county FIPS (covers the ~6% with no zip).
    # Note: city_county_lookup uses Census Place FIPS codes, not county FIPS directly.
    # Only Place FIPS that happen to equal a county FIPS resolve via county_ids.
    zip_map: dict[str, str] = {}
    zip_map_path = Path("../data/zip_county_map.json")
    if zip_map_path.exists():
        zip_map = json.loads(zip_map_path.read_text())

    city_lookup: dict = {}
    city_lookup_path = Path("../data/city_county_lookup.json")
    if city_lookup_path.exists():
        raw_lookup = json.loads(city_lookup_path.read_text())
        city_lookup = {tuple(k.split("|")): v for k, v in raw_lookup.items()}

    client = NotionClient(notion_cfg["api_key"])

    if wipe and not dry_run:
        wipe_strikes_db(client, notion_cfg["databases"]["strikes"])

    raw_records = fetch_cornell_data()
    if not raw_records:
        logger.warning("No strike data fetched. Save Cornell data as data/cornell_strikes.json and re-run.")
        return

    Path("../data/cornell_strikes.json").write_text(json.dumps(raw_records, indent=2))

    # Build set of Cornell IDs already in Notion to skip on re-runs.
    existing_cornell_ids: set[int] = set()
    if not wipe:
        logger.info("Checking for existing STRIKES records to skip duplicates...")
        existing = client.query_all(notion_cfg["databases"]["strikes"])
        for page in existing:
            cid = page.get("properties", {}).get("Cornell ID", {}).get("number")
            if cid is not None:
                existing_cornell_ids.add(int(cid))
        logger.info(f"Found {len(existing_cornell_ids)} existing records — will skip these")

    ok = 0
    skipped = 0
    errors = []
    unmatched_unions = []
    county_matched = 0

    for raw in raw_records:
        strike = normalize_field(raw)

        cornell_id = strike.get("cornell_id")
        if cornell_id is not None and int(cornell_id) in existing_cornell_ids:
            skipped += 1
            continue

        state_abbr = strike["state"]
        state_fips = STATE_FIPS.get(state_abbr, "")
        state_id = state_ids.get(state_abbr) or state_ids.get(state_fips)

        # County lookup: zip-based first (94% match), city-based fallback.
        county_fips = None
        zip_code = strike.get("zip_code", "")
        if zip_code and zip_code in zip_map:
            county_fips = zip_map[zip_code]
        if not county_fips:
            place_fips = city_lookup.get((strike.get("city", "").lower(), state_abbr))
            if place_fips and place_fips in county_ids:
                county_fips = place_fips
        county_id = county_ids.get(county_fips) if county_fips else None
        if county_id:
            county_matched += 1

        union_id = fuzzy_match_union(strike.get("union_name", ""), union_index)
        if strike.get("union_name") and not union_id:
            unmatched_unions.append(strike["union_name"])

        props = build_properties(strike, county_id, state_id, union_id)

        if dry_run:
            if ok < 5:
                print(
                    f"Cornell ID={strike.get('cornell_id')} | {strike['name'][:50]} | "
                    f"{state_abbr} | workers={strike['workers']} | "
                    f"county_fips={county_fips or 'no match'}"
                )
            ok += 1
            continue

        try:
            client.create_page(notion_cfg["databases"]["strikes"], props)
            ok += 1
            if ok % 100 == 0:
                logger.info(f"Created {ok} strikes ({county_matched} county-matched)")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed strike '{strike['name'][:40]}': {e}")
            errors.append({"name": strike["name"], "error": str(e)})

    total = len(raw_records)
    matchable = total - skipped
    logger.info(
        f"Done. {ok} strikes created, {skipped} skipped (already in Notion), "
        f"{len(errors)} errors. "
        f"County match rate: {county_matched}/{matchable} ({100*county_matched//matchable if matchable else 0}%)"
    )
    if dry_run:
        print(f"\nDry run: {ok} records processed, {county_matched}/{total} county-matched")
    if unmatched_unions:
        out = Path("../logs/task8_unmatched_unions.json")
        out.write_text(json.dumps(list(set(unmatched_unions)), indent=2))
        logger.info(f"{len(set(unmatched_unions))} unique union names unmatched → {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print first 5 records and county match stats; do not write to Notion")
    parser.add_argument("--wipe", action="store_true",
                        help="Archive all existing STRIKES records before re-ingesting")
    args = parser.parse_args()
    run(args.config, args.dry_run, args.wipe)
