"""
P2-2: Add EMS / Emergency Ambulance sector and pull CBP employment.

Steps:
  1. Create SECTORS DB record for Healthcare - EMS (NAICS 621910, SVS=100)
  2. Pull Census CBP employment for NAICS 621910 for all counties
  3. Write EMPLOYMENT DB records linked to the new EMS sector

Architecture note (Option B, approved Sam 2026-05-04):
  NAICS 621910 employment is a subset of existing NAICS 621 (Ambulatory) records.
  We do NOT modify existing 621 records. The resulting double-count =
  emp_621910 × SVS_621(=10) per county — small in absolute terms since SVS_621 is
  near-floor. Documented as a known limitation in methodology.

CBP suppression note:
  6-digit NAICS codes have higher suppression rates than 3-digit in CBP.
  Rural counties with <3 EMS establishments will show suppressed/missing data.
  These counties get no EMS record (treated as zero employment for scoring).

Usage:
    python task_p2_ems_employment.py --config ../config.json [--dry-run] [--spot-check]
    --spot-check: fetch 10 counties only, print results, do not write to Notion
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / "logs" / "task_p2_ems.log"),
    ],
)
logger = logging.getLogger(__name__)

CBP_API = "https://api.census.gov/data/2023/cbp"
CBP_YEAR = "2023"
EMS_NAICS = "621910"

# SVS formula check (from Decisions Log, confirmed final 2026-05-04):
# Chokepoint(25) + Crisis-Creating(20) + McAlevey(20) + Community-Facing(15) + Non-Off(10) = 90
# Multiplier: Chokepoint=YES AND Community-Facing=YES → ×1.15 = 103.5 → cap = 100
EMS_SVS = 100


def ems_sector_properties() -> dict:
    """Build SECTORS DB properties for the EMS sector record."""
    return {
        "Sector Name": title_prop("Healthcare - EMS / Emergency Ambulance"),
        "NAICS Code": text_prop(EMS_NAICS),
        "Sector Type": select_prop("Healthcare"),
        "Non-Offshoreable": checkbox_prop(True),
        "Crisis-Creating": checkbox_prop(True),
        "Community-Facing": checkbox_prop(True),
        "Chokepoint Potential": checkbox_prop(True),
        "Strategic Value Score": number_prop(EMS_SVS),
        "US Total Employment": number_prop(260_000),
        "Avg Union Density %": number_prop(4.2),
        "Organizability": select_prop("High"),
        "McAlevey Priority": checkbox_prop(True),
        "Description": {
            "rich_text": [{
                "text": {
                    "content": (
                        "Emergency ambulance services, air ambulance. Private EMS companies "
                        "(e.g. AMR/Global Medical Response) are active organizing targets. "
                        "NOTE: Employment is a subset of NAICS 621 (Ambulatory). Small "
                        "double-count accepted per P2-2 Option B decision."
                    )
                }
            }]
        },
    }


def fetch_ems_employment(state_fips: str, county_fips: str) -> Optional[int]:
    """
    Fetch CBP employment for NAICS 621910 in one county.
    Returns None if suppressed or not available.
    """
    params = {
        "get": "EMP,NAICS2017",
        "for": f"county:{county_fips}",
        "in": f"state:{state_fips}",
        "NAICS2017": EMS_NAICS,
    }
    try:
        resp = requests.get(CBP_API, params=params, timeout=30)
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        data = resp.json()
        for row in data[1:]:
            emp_val = row[0]
            if emp_val not in ("", "N", None):
                return int(emp_val)
        return None
    except Exception as e:
        logger.debug(f"CBP fetch {state_fips}/{county_fips}: {e}")
        return None


def build_employment_record(fips: str, emp: int,
                             county_id: str, sector_id: str,
                             state_id: Optional[str] = None) -> dict:
    props = {
        "Record ID": title_prop(f"{fips}-{EMS_NAICS}"),
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


FIPS_TO_STATE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY",
}


def run(config_path: str, dry_run: bool = False, spot_check: bool = False):
    config = json.loads(Path(config_path).read_text())
    notion_cfg = config["notion"]

    county_ids: dict = json.loads((Path(config_path).parent / "data" / "county_ids.json").read_text())
    sector_ids: dict = json.loads((Path(config_path).parent / "data" / "sector_ids.json").read_text())
    state_ids_path = Path(config_path).parent / "data" / "state_ids.json"
    state_ids: dict = json.loads(state_ids_path.read_text()) if state_ids_path.exists() else {}

    if not dry_run:
        client = NotionClient(notion_cfg["api_key"])

    # ── Step 1: Create or find EMS sector record ──────────────────────────
    if EMS_NAICS in sector_ids:
        ems_sector_id = sector_ids[EMS_NAICS]
        logger.info(f"EMS sector already in sector_ids.json: {ems_sector_id}")
    elif dry_run or spot_check:
        ems_sector_id = "DRY_RUN_SECTOR_ID"
        logger.info("Dry/spot-check run: skipping sector creation")
    else:
        logger.info("Creating EMS sector record in SECTORS DB...")
        result = client.create_page(notion_cfg["databases"]["sectors"], ems_sector_properties())
        ems_sector_id = result["id"]
        sector_ids[EMS_NAICS] = ems_sector_id
        sector_ids_path = Path(config_path).parent / "data" / "sector_ids.json"
        sector_ids_path.write_text(json.dumps(sector_ids, indent=2))
        logger.info(f"EMS sector created: {ems_sector_id}")
        time.sleep(0.5)

    # ── Step 2: Skip counties with existing EMS employment records ────────
    existing_record_ids: set[str] = set()
    if not dry_run and not spot_check:
        logger.info("Checking for existing EMS employment records...")
        existing = client.query_all(notion_cfg["databases"]["employment"])
        for rec in existing:
            title = rec.get("properties", {}).get("Record ID", {}).get("title", [])
            if title:
                rid = title[0]["text"]["content"]
                if EMS_NAICS in rid:
                    existing_record_ids.add(rid)
        if existing_record_ids:
            logger.info(f"Skipping {len(existing_record_ids)} existing EMS records")

    # ── Step 3: Pull CBP and create employment records ────────────────────
    all_fips = list(county_ids.keys())
    if spot_check:
        # Use a mix: a few large urban + a few rural for suppression testing
        spot_fips = ["42101", "17031", "06037", "36061", "48201",  # Philly, Cook, LA, NYC, Harris
                     "30003", "38065", "46035", "56039", "02016"]  # MT, ND, SD, WY, AK rural
        all_fips = [f for f in spot_fips if f in county_ids]
        logger.info(f"Spot check: {len(all_fips)} counties")

    ok = 0
    skipped = 0
    suppressed = 0
    errors = []

    for i, fips in enumerate(all_fips, 1):
        record_id = f"{fips}-{EMS_NAICS}"
        if record_id in existing_record_ids:
            skipped += 1
            continue

        county_id = county_ids[fips]
        state_fips_str = fips[:2]
        county_fips_str = fips[2:]
        state_abbr = FIPS_TO_STATE.get(state_fips_str, "")
        state_id = state_ids.get(state_abbr) or state_ids.get(state_fips_str)

        emp = fetch_ems_employment(state_fips_str, county_fips_str)

        if emp is None:
            suppressed += 1
            if spot_check:
                print(f"  {fips}: SUPPRESSED/MISSING")
            continue

        if dry_run or spot_check:
            print(f"  {fips}: EMS employment = {emp}")
            ok += 1
            continue

        props = build_employment_record(fips, emp, county_id, ems_sector_id, state_id)
        try:
            client.create_page(notion_cfg["databases"]["employment"], props)
            ok += 1
            if ok % 100 == 0:
                logger.info(f"Created {ok} EMS records ({suppressed} suppressed so far)")
        except Exception as e:
            logger.error(f"Notion error {fips}: {e}")
            errors.append({"fips": fips, "error": str(e)})

        time.sleep(0.4)

        if i % 200 == 0:
            logger.info(f"Progress: {i}/{len(all_fips)} counties")

    total = len(all_fips)
    logger.info(
        f"Done. {ok} EMS records created, {skipped} skipped (existing), "
        f"{suppressed} suppressed/missing ({100*suppressed//total if total else 0}% of counties), "
        f"{len(errors)} errors"
    )
    if spot_check:
        print(f"\nSpot check: {ok} data points, {suppressed}/{total} suppressed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--spot-check", action="store_true",
                        help="Test 10 counties (5 urban + 5 rural) without writing to Notion")
    args = parser.parse_args()
    run(args.config, args.dry_run, args.spot_check)
