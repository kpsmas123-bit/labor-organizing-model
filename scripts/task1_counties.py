"""
Task 1: Initialize County Database
Downloads Census Bureau county population estimates and uploads all 3,143
counties to the Notion COUNTIES database.

Usage:
    python task1_counties.py [--config /path/to/config.json] [--dry-run]
"""

import csv
import io
import json
import logging
import argparse
import time
from pathlib import Path

import requests

import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import (
    NotionClient, title_prop, text_prop, number_prop,
    select_prop, checkbox_prop
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                               logging.FileHandler("../logs/task1_counties.log")])
logger = logging.getLogger(__name__)

CENSUS_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/counties/totals/co-est2023-alldata.csv"

REGION_MAP = {
    "1": "Northeast",
    "2": "Midwest",
    "3": "South",
    "4": "West",
}

DIVISION_MAP = {
    "1": "New England",
    "2": "Middle Atlantic",
    "3": "East North Central",
    "4": "West North Central",
    "5": "South Atlantic",
    "6": "East South Central",
    "7": "West South Central",
    "8": "Mountain",
    "9": "Pacific",
}

SWING_STATES = {"AZ", "GA", "MI", "NV", "NC", "PA", "WI"}

STATE_ABBR = {
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

RURAL_URBAN_MAP = {
    # Based on population thresholds; refined scoring uses USDA rural codes
    "urban": "Urban",
    "rural": "Rural",
}


def download_census_data() -> list[dict]:
    logger.info(f"Downloading Census data from {CENSUS_URL}")
    resp = requests.get(CENSUS_URL, timeout=120)
    resp.raise_for_status()
    # Census file is latin-1 encoded
    content = resp.content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def classify_rural_urban(pop: int) -> str:
    if pop >= 50000:
        return "Urban"
    elif pop >= 10000:
        return "Mixed"
    return "Rural"


def parse_counties(rows: list[dict]) -> list[dict]:
    counties = []
    for row in rows:
        # SUMLEV 050 = county; skip state-level rows (SUMLEV 040)
        if row.get("SUMLEV", "").strip() != "050":
            continue
        state_fips = row["STATE"].zfill(2)
        county_fips = row["COUNTY"].zfill(3)
        fips = state_fips + county_fips

        state_name = row["STNAME"].strip()
        county_name = row["CTYNAME"].strip()
        pop = int(row.get("POPESTIMATE2023", 0) or 0)

        state_abbr = STATE_ABBR.get(state_name, "")
        region = REGION_MAP.get(row.get("REGION", "").strip(), "Unknown")
        division = DIVISION_MAP.get(row.get("DIVISION", "").strip(), "Unknown")

        counties.append({
            "county_name": county_name,
            "state": state_abbr,
            "state_name": state_name,
            "fips": fips,
            "population": pop,
            "region": region,
            "division": division,
            "swing_state": state_abbr in SWING_STATES,
            "rural_urban": classify_rural_urban(pop),
        })

    logger.info(f"Parsed {len(counties)} counties")
    return counties


def build_properties(county: dict) -> dict:
    return {
        "County Name": title_prop(county["county_name"]),
        "FIPS Code": text_prop(county["fips"]),
        "Population": number_prop(county["population"]),
        "Region": select_prop(county["region"]),
        "Census Division": select_prop(county["division"]),
        "Rural/Urban": select_prop(county["rural_urban"]),
        "Swing State": checkbox_prop(county["swing_state"]),
        "Data Quality": select_prop("Medium"),
    }


def run(config_path: str, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    db_id = config["notion"]["databases"]["counties"]

    if not dry_run:
        client = NotionClient(config["notion"]["api_key"])

    rows = download_census_data()
    counties = parse_counties(rows)

    ok = 0
    errors = []
    for i, county in enumerate(counties, 1):
        props = build_properties(county)
        if dry_run:
            if i <= 3:
                print(json.dumps({"county": county["county_name"], "props_keys": list(props)}, indent=2))
            ok += 1
            continue
        try:
            client.create_page(db_id, props)
            ok += 1
            if i % 100 == 0:
                logger.info(f"Progress: {i}/{len(counties)} counties uploaded")
            # Notion allows ~3 req/s; stay well under
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed {county['fips']} {county['county_name']}: {e}")
            errors.append({"fips": county["fips"], "name": county["county_name"], "error": str(e)})

    logger.info(f"Done. {ok} uploaded, {len(errors)} errors")
    if errors:
        err_path = Path("../logs/task1_errors.json")
        err_path.write_text(json.dumps(errors, indent=2))
        logger.info(f"Errors saved to {err_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.config, args.dry_run)
