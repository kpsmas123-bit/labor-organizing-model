"""
Task 4: Collect County × Sector Employment Data
Source: Census County Business Patterns (CBP) API — annual employment by NAICS at county level.
Builds employment records in the Notion EMPLOYMENT database.

Phases:
  --phase 1  Top 100 counties by population (~60% of US population)
  --phase 2  Next 400 counties (~90%)
  --phase 3  Remaining counties

Usage:
    python task4_bls_employment.py --config ../config.json --phase 1 [--dry-run]
"""

import json
import logging
import argparse
import time
from pathlib import Path
from typing import Optional

import requests
import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import (
    NotionClient, title_prop, text_prop, number_prop,
    select_prop, checkbox_prop, relation_prop
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                               logging.FileHandler("../logs/task4_employment.log")])
logger = logging.getLogger(__name__)

CBP_API = "https://api.census.gov/data/2023/cbp"
CBP_YEAR = "2023"

# CBP-compatible NAICS codes for our 17 private sectors
# Government sectors (9211/9221/9231) are not in CBP — skipped here.
# 33 (mfg durable) → use 31-33 (total mfg); 44+45 (retail) → use 44-45 (combined)
NAICS_CODES = [
    "622", "623", "6216", "621",       # Healthcare
    "6111", "6113", "6112",            # Education
    "493", "484", "492", "488",        # Logistics
    "721", "722",                      # Hospitality
    "236", "237", "238",               # Construction
    "31-33",                           # Manufacturing (all; proxy for durable goods)
    "44-45",                           # Retail
    "221",                             # Utilities
]

# Map CBP NAICS back to sector_ids keys (which use the original NAICS from task3)
CBP_TO_SECTOR_NAICS = {
    "622": "622", "623": "623", "6216": "6216", "621": "621",
    "6111": "6111", "6113": "6113", "6112": "6112",
    "493": "493", "484": "484", "492": "492", "488": "488",
    "721": "721", "722": "722",
    "236": "236-238", "237": "236-238", "238": "236-238",  # all map to Building Trades page
    "31-33": "33",    # sector_ids key is "33" (Manufacturing - Durable Goods)
    "44-45": "44-45", # sector_ids key is "44-45" (Retail - General)
    "221": "221",
}


def fetch_county_employment(state_fips: str, county_fips: str) -> dict:
    """One CBP API call returns all NAICS employment for a county."""
    params = {
        "get": "EMP,ESTAB,NAICS2017",
        "for": f"county:{county_fips}",
        "in": f"state:{state_fips}",
    }
    resp = requests.get(CBP_API, params=params, timeout=30)
    resp.raise_for_status()
    if resp.status_code == 204:
        return {}
    data = resp.json()
    # data[0] is header row; rest are data rows
    emp_by_naics = {}
    for row in data[1:]:
        emp_by_naics[row[2]] = int(row[0]) if row[0] not in ("", "N", None) else None
    return emp_by_naics


def build_employment_record(fips: str, naics: str, emp: int,
                             county_id: str, sector_id: str,
                             state_id: Optional[str] = None) -> dict:
    props = {
        "Record ID": title_prop(f"{fips}-{naics}"),
        "County": relation_prop([county_id]),
        "Sector": relation_prop([sector_id]),
        "Total Employment": number_prop(emp),
        "Year": number_prop(int(CBP_YEAR)),
        "Source": text_prop(f"Census CBP {CBP_YEAR}"),
        "BLS Disclosure Flag": checkbox_prop(False),
        "Confidence": select_prop("High"),
    }
    if state_id:
        props["State"] = relation_prop([state_id])
    return props


def run(config_path: str, phase: int, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    notion_cfg = config["notion"]

    if not dry_run:
        client = NotionClient(notion_cfg["api_key"])

    county_ids_path = Path("../data/county_ids.json")
    sector_ids_path = Path("../data/sector_ids.json")
    state_ids_path = Path("../data/state_ids.json")

    if not county_ids_path.exists():
        logger.error("county_ids.json not found. Run task1 first.")
        return
    if not sector_ids_path.exists():
        logger.error("sector_ids.json not found. Run task3 first.")
        return

    county_ids: dict = json.loads(county_ids_path.read_text())
    sector_ids: dict = json.loads(sector_ids_path.read_text())
    state_ids: dict = json.loads(state_ids_path.read_text()) if state_ids_path.exists() else {}

    all_fips = list(county_ids.keys())
    priority = config["priority_counties"]["phase_1_top_100"]

    if phase == 1:
        fips_list = [f for f in priority if f in county_ids][:100]
    elif phase == 2:
        done = set(priority[:100])
        fips_list = [f for f in all_fips if f not in done][:400]
    else:
        done = set(priority[:100]) | set([f for f in all_fips if f not in set(priority[:100])][:400])
        fips_list = [f for f in all_fips if f not in done]

    logger.info(f"Phase {phase}: {len(fips_list)} counties × {len(NAICS_CODES)} sectors (CBP {CBP_YEAR})")

    # Build set of already-uploaded record IDs to skip on re-runs
    if not dry_run:
        logger.info("Fetching existing record IDs to skip duplicates...")
        existing = client.query_all(notion_cfg["databases"]["employment"])
        existing_ids = set()
        for rec in existing:
            title = rec.get("properties", {}).get("Record ID", {}).get("title", [])
            if title:
                existing_ids.add(title[0]["text"]["content"])
        logger.info(f"Found {len(existing_ids)} existing records — will skip these")
    else:
        existing_ids = set()

    ok = 0
    skipped = 0
    suppressed = 0
    errors = []

    for i, fips in enumerate(fips_list, 1):
        county_id = county_ids[fips]
        state_fips = fips[:2]
        county_fips = fips[2:]
        state_id = state_ids.get(state_fips)

        if dry_run:
            logger.info(f"[DRY RUN] {fips} state={state_fips} county={county_fips}")
            continue

        try:
            emp_by_naics = fetch_county_employment(state_fips, county_fips)
        except Exception as e:
            logger.error(f"CBP fetch failed for {fips}: {e}")
            errors.append({"fips": fips, "error": str(e)})
            time.sleep(2)
            continue

        for cbp_naics in NAICS_CODES:
            record_id = f"{fips}-{cbp_naics}"
            if record_id in existing_ids:
                skipped += 1
                continue

            emp = emp_by_naics.get(cbp_naics)
            if emp is None:
                suppressed += 1
                continue

            sector_naics_key = CBP_TO_SECTOR_NAICS[cbp_naics]
            sector_id = sector_ids.get(sector_naics_key)
            if not sector_id:
                logger.debug(f"No sector_id for naics={sector_naics_key}, skipping")
                suppressed += 1
                continue

            props = build_employment_record(fips, cbp_naics, emp, county_id, sector_id, state_id)
            try:
                client.create_page(notion_cfg["databases"]["employment"], props)
                ok += 1
            except Exception as e:
                logger.error(f"Notion error {fips}-{cbp_naics}: {e}")
                errors.append({"fips": fips, "naics": cbp_naics, "error": str(e)})

        if i % 10 == 0:
            logger.info(f"Progress: {i}/{len(fips_list)} counties, {ok} records created")

        # CBP rate limit: ~4 req/s is safe; Notion allows ~3 req/s
        time.sleep(0.4)

    logger.info(f"Phase {phase} done: {ok} new records, {skipped} skipped (already existed), {suppressed} suppressed/missing, {len(errors)} errors")
    if errors:
        out = Path(f"../logs/task4_phase{phase}_errors.json")
        out.write_text(json.dumps(errors, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--phase", type=int, default=1, choices=[1, 2, 3])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.config, args.phase, args.dry_run)
