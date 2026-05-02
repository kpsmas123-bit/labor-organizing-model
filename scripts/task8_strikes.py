"""
Task 8: Scrape Cornell ILR Labor Action Tracker for US strikes 2019-2024.
Uploads records to Notion STRIKES database and attempts fuzzy-matching to UNIONS.

Cornell tracker: https://striketracker.ilr.cornell.edu/
Data is loaded client-side via API; we target the JSON endpoint.

Usage:
    python task8_strikes.py --config ../config.json [--dry-run]
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

# Cornell tracker may serve data from this endpoint (inspect network tab to confirm)
CORNELL_DATA_URL = "https://striketracker.ilr.cornell.edu/labor_actions.json"
CORNELL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (research purposes; contact labor-data@example.com)",
    "Accept": "application/json",
}

STATE_ABBR_TO_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


def fetch_cornell_data() -> list[dict]:
    """Fetch strike data from Cornell ILR Labor Action Tracker static JSON."""
    local = Path("../data/cornell_strikes.json")
    try:
        resp = requests.get(CORNELL_DATA_URL, headers=CORNELL_HEADERS, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        # Response is a dict keyed by record ID; values are the records
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
    # Location: first entry in locations list
    locations = raw.get("locations") or []
    loc = locations[0] if locations else {}
    city = loc.get("City") or loc.get("city") or ""
    state = loc.get("State") or loc.get("state") or ""

    # Industry: list or string
    industry_raw = raw.get("Industry") or raw.get("industry") or ""
    industry = (industry_raw[0] if isinstance(industry_raw, list) and industry_raw
                else str(industry_raw))

    # Demands: list → joined string
    demands_raw = raw.get("Worker_demands") or raw.get("worker_demands") or []
    demands = ", ".join(demands_raw) if isinstance(demands_raw, list) else str(demands_raw)

    # Sources: first URL
    sources = raw.get("sources") or []
    source_url = sources[0] if sources else ""

    workers_raw = raw.get("Approximate_Number_of_Participants") or raw.get("number_of_workers") or 0
    try:
        workers = int(float(workers_raw))
    except (TypeError, ValueError):
        workers = 0

    return {
        "name": raw.get("Employer") or raw.get("employer") or "Unknown Strike",
        "union_name": raw.get("Labor_Organization") or raw.get("labor_organization") or "",
        "employer": raw.get("Employer") or raw.get("employer") or "",
        "city": city,
        "state": state,
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


def run(config_path: str, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    notion_cfg = config["notion"]

    county_ids: dict[str, str] = {}
    state_ids: dict[str, str] = {}
    union_index: dict[str, str] = {}  # union name lower → page_id

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

    city_lookup_path = Path("../data/city_county_lookup.json")
    city_lookup: dict = {}
    if city_lookup_path.exists():
        raw = json.loads(city_lookup_path.read_text())
        city_lookup = {tuple(k.split("|")): v for k, v in raw.items()}

    if not dry_run:
        client = NotionClient(notion_cfg["api_key"])

    raw_records = fetch_cornell_data()
    if not raw_records:
        logger.warning("No strike data fetched. Save Cornell data as data/cornell_strikes.json and re-run.")
        return

    # Cache locally for re-runs
    Path("../data/cornell_strikes.json").write_text(json.dumps(raw_records, indent=2))

    ok = 0
    errors = []
    unmatched_unions = []

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

    for raw in raw_records:
        strike = normalize_field(raw)

        state_abbr = strike["state"].upper()[:2] if strike.get("state") else ""
        state_fips = STATE_FIPS.get(state_abbr, "")
        state_id = state_ids.get(state_abbr) or state_ids.get(state_fips)

        city_key = (strike.get("city", "").lower(), state_abbr)
        county_fips = city_lookup.get(city_key)
        county_id = county_ids.get(county_fips) if county_fips else None

        union_id = fuzzy_match_union(strike.get("union_name", ""), union_index)
        if strike.get("union_name") and not union_id:
            unmatched_unions.append(strike["union_name"])

        props = build_properties(strike, county_id, state_id, union_id)

        if dry_run:
            if ok < 5:
                print(f"{strike['name'][:60]} | {state_abbr} | workers={strike['workers']}")
            ok += 1
            continue

        try:
            client.create_page(notion_cfg["databases"]["strikes"], props)
            ok += 1
            if ok % 500 == 0:
                logger.info(f"Created {ok} strikes")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed strike '{strike['name'][:40]}': {e}")
            errors.append({"name": strike["name"], "error": str(e)})

    logger.info(f"Done. {ok} strikes created, {len(errors)} errors")
    if unmatched_unions:
        out = Path("../logs/task8_unmatched_unions.json")
        out.write_text(json.dumps(list(set(unmatched_unions)), indent=2))
        logger.info(f"{len(set(unmatched_unions))} unique union names unmatched → {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.config, args.dry_run)
