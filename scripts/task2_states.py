"""
Task 2: Initialize States Database
Creates 51 records (50 states + DC) in the Notion STATES database,
merging Census population data with hardcoded electoral/labor fields.

Usage:
    python task2_states.py [--config /path/to/config.json] [--dry-run]
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
                               logging.FileHandler("../logs/task2_states.log")])
logger = logging.getLogger(__name__)

CENSUS_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/counties/totals/co-est2023-alldata.csv"

SWING_STATES = {"AZ", "GA", "MI", "NV", "NC", "PA", "WI"}

# 2024 presidential results + metadata
STATE_DATA = {
    "AL": {"name": "Alabama", "fips": "01", "ev": 9, "winner_2024": "Republican", "margin_2024": -27.2, "trifecta": "Republican", "region": "South"},
    "AK": {"name": "Alaska", "fips": "02", "ev": 3, "winner_2024": "Republican", "margin_2024": -13.3, "trifecta": "Republican", "region": "West"},
    "AZ": {"name": "Arizona", "fips": "04", "ev": 11, "winner_2024": "Republican", "margin_2024": -5.4, "trifecta": "Republican", "region": "West"},
    "AR": {"name": "Arkansas", "fips": "05", "ev": 6, "winner_2024": "Republican", "margin_2024": -28.4, "trifecta": "Republican", "region": "South"},
    "CA": {"name": "California", "fips": "06", "ev": 54, "winner_2024": "Democratic", "margin_2024": 20.2, "trifecta": "Democratic", "region": "West"},
    "CO": {"name": "Colorado", "fips": "08", "ev": 10, "winner_2024": "Democratic", "margin_2024": 11.0, "trifecta": "Democratic", "region": "West"},
    "CT": {"name": "Connecticut", "fips": "09", "ev": 7, "winner_2024": "Democratic", "margin_2024": 13.5, "trifecta": "Democratic", "region": "Northeast"},
    "DE": {"name": "Delaware", "fips": "10", "ev": 3, "winner_2024": "Democratic", "margin_2024": 12.8, "trifecta": "Democratic", "region": "Northeast"},
    "DC": {"name": "District of Columbia", "fips": "11", "ev": 3, "winner_2024": "Democratic", "margin_2024": 76.1, "trifecta": "Democratic", "region": "South"},
    "FL": {"name": "Florida", "fips": "12", "ev": 30, "winner_2024": "Republican", "margin_2024": -13.1, "trifecta": "Republican", "region": "South"},
    "GA": {"name": "Georgia", "fips": "13", "ev": 16, "winner_2024": "Republican", "margin_2024": -2.1, "trifecta": "Republican", "region": "South"},
    "HI": {"name": "Hawaii", "fips": "15", "ev": 4, "winner_2024": "Democratic", "margin_2024": 28.4, "trifecta": "Democratic", "region": "West"},
    "ID": {"name": "Idaho", "fips": "16", "ev": 4, "winner_2024": "Republican", "margin_2024": -30.5, "trifecta": "Republican", "region": "West"},
    "IL": {"name": "Illinois", "fips": "17", "ev": 19, "winner_2024": "Democratic", "margin_2024": 14.4, "trifecta": "Democratic", "region": "Midwest"},
    "IN": {"name": "Indiana", "fips": "18", "ev": 11, "winner_2024": "Republican", "margin_2024": -18.4, "trifecta": "Republican", "region": "Midwest"},
    "IA": {"name": "Iowa", "fips": "19", "ev": 6, "winner_2024": "Republican", "margin_2024": -13.5, "trifecta": "Republican", "region": "Midwest"},
    "KS": {"name": "Kansas", "fips": "20", "ev": 6, "winner_2024": "Republican", "margin_2024": -19.8, "trifecta": "Republican", "region": "Midwest"},
    "KY": {"name": "Kentucky", "fips": "21", "ev": 8, "winner_2024": "Republican", "margin_2024": -29.1, "trifecta": "Republican", "region": "South"},
    "LA": {"name": "Louisiana", "fips": "22", "ev": 8, "winner_2024": "Republican", "margin_2024": -19.7, "trifecta": "Republican", "region": "South"},
    "ME": {"name": "Maine", "fips": "23", "ev": 4, "winner_2024": "Democratic", "margin_2024": 7.0, "trifecta": "Democratic", "region": "Northeast"},
    "MD": {"name": "Maryland", "fips": "24", "ev": 10, "winner_2024": "Democratic", "margin_2024": 32.6, "trifecta": "Democratic", "region": "South"},
    "MA": {"name": "Massachusetts", "fips": "25", "ev": 11, "winner_2024": "Democratic", "margin_2024": 28.5, "trifecta": "Democratic", "region": "Northeast"},
    "MI": {"name": "Michigan", "fips": "26", "ev": 15, "winner_2024": "Republican", "margin_2024": -1.4, "trifecta": "Divided", "region": "Midwest"},
    "MN": {"name": "Minnesota", "fips": "27", "ev": 10, "winner_2024": "Democratic", "margin_2024": 3.5, "trifecta": "Democratic", "region": "Midwest"},
    "MS": {"name": "Mississippi", "fips": "28", "ev": 6, "winner_2024": "Republican", "margin_2024": -17.2, "trifecta": "Republican", "region": "South"},
    "MO": {"name": "Missouri", "fips": "29", "ev": 10, "winner_2024": "Republican", "margin_2024": -18.2, "trifecta": "Republican", "region": "Midwest"},
    "MT": {"name": "Montana", "fips": "30", "ev": 4, "winner_2024": "Republican", "margin_2024": -20.7, "trifecta": "Republican", "region": "West"},
    "NE": {"name": "Nebraska", "fips": "31", "ev": 5, "winner_2024": "Republican", "margin_2024": -18.3, "trifecta": "Divided", "region": "Midwest"},
    "NV": {"name": "Nevada", "fips": "32", "ev": 6, "winner_2024": "Republican", "margin_2024": -3.1, "trifecta": "Divided", "region": "West"},
    "NH": {"name": "New Hampshire", "fips": "33", "ev": 4, "winner_2024": "Democratic", "margin_2024": 2.1, "trifecta": "Divided", "region": "Northeast"},
    "NJ": {"name": "New Jersey", "fips": "34", "ev": 14, "winner_2024": "Democratic", "margin_2024": 5.6, "trifecta": "Divided", "region": "Northeast"},
    "NM": {"name": "New Mexico", "fips": "35", "ev": 5, "winner_2024": "Democratic", "margin_2024": 10.7, "trifecta": "Democratic", "region": "West"},
    "NY": {"name": "New York", "fips": "36", "ev": 28, "winner_2024": "Democratic", "margin_2024": 11.0, "trifecta": "Democratic", "region": "Northeast"},
    "NC": {"name": "North Carolina", "fips": "37", "ev": 16, "winner_2024": "Republican", "margin_2024": -3.1, "trifecta": "Divided", "region": "South"},
    "ND": {"name": "North Dakota", "fips": "38", "ev": 3, "winner_2024": "Republican", "margin_2024": -33.3, "trifecta": "Republican", "region": "Midwest"},
    "OH": {"name": "Ohio", "fips": "39", "ev": 17, "winner_2024": "Republican", "margin_2024": -11.0, "trifecta": "Republican", "region": "Midwest"},
    "OK": {"name": "Oklahoma", "fips": "40", "ev": 7, "winner_2024": "Republican", "margin_2024": -32.0, "trifecta": "Republican", "region": "South"},
    "OR": {"name": "Oregon", "fips": "41", "ev": 8, "winner_2024": "Democratic", "margin_2024": 13.1, "trifecta": "Democratic", "region": "West"},
    "PA": {"name": "Pennsylvania", "fips": "42", "ev": 19, "winner_2024": "Republican", "margin_2024": -1.8, "trifecta": "Divided", "region": "Northeast"},
    "RI": {"name": "Rhode Island", "fips": "44", "ev": 4, "winner_2024": "Democratic", "margin_2024": 21.2, "trifecta": "Democratic", "region": "Northeast"},
    "SC": {"name": "South Carolina", "fips": "45", "ev": 9, "winner_2024": "Republican", "margin_2024": -13.9, "trifecta": "Republican", "region": "South"},
    "SD": {"name": "South Dakota", "fips": "46", "ev": 3, "winner_2024": "Republican", "margin_2024": -27.4, "trifecta": "Republican", "region": "Midwest"},
    "TN": {"name": "Tennessee", "fips": "47", "ev": 11, "winner_2024": "Republican", "margin_2024": -23.7, "trifecta": "Republican", "region": "South"},
    "TX": {"name": "Texas", "fips": "48", "ev": 40, "winner_2024": "Republican", "margin_2024": -14.1, "trifecta": "Republican", "region": "South"},
    "UT": {"name": "Utah", "fips": "49", "ev": 6, "winner_2024": "Republican", "margin_2024": -12.9, "trifecta": "Republican", "region": "West"},
    "VT": {"name": "Vermont", "fips": "50", "ev": 3, "winner_2024": "Democratic", "margin_2024": 36.1, "trifecta": "Democratic", "region": "Northeast"},
    "VA": {"name": "Virginia", "fips": "51", "ev": 13, "winner_2024": "Democratic", "margin_2024": 6.3, "trifecta": "Democratic", "region": "South"},
    "WA": {"name": "Washington", "fips": "53", "ev": 12, "winner_2024": "Democratic", "margin_2024": 18.3, "trifecta": "Democratic", "region": "West"},
    "WV": {"name": "West Virginia", "fips": "54", "ev": 4, "winner_2024": "Republican", "margin_2024": -38.5, "trifecta": "Republican", "region": "South"},
    "WI": {"name": "Wisconsin", "fips": "55", "ev": 10, "winner_2024": "Republican", "margin_2024": -0.9, "trifecta": "Divided", "region": "Midwest"},
    "WY": {"name": "Wyoming", "fips": "56", "ev": 3, "winner_2024": "Republican", "margin_2024": -42.6, "trifecta": "Republican", "region": "West"},
}


def get_state_populations() -> dict[str, int]:
    """Pull state-level population from the same Census county file (SUMLEV 040)."""
    logger.info("Fetching state populations from Census Bureau")
    resp = requests.get(CENSUS_URL, timeout=120)
    resp.raise_for_status()
    content = resp.content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(content))

    from scripts.task1_counties import STATE_ABBR
    pops = {}
    for row in reader:
        if row.get("SUMLEV", "").strip() != "040":
            continue
        state_name = row["STNAME"].strip()
        abbr = STATE_ABBR.get(state_name, "")
        if abbr:
            pops[abbr] = int(row.get("POPESTIMATE2023", 0) or 0)
    return pops


def build_properties(abbr: str, info: dict, pop: int, density: dict) -> dict:
    return {
        "State Name": title_prop(info["name"]),
        "State Abbr": text_prop(abbr),
        "FIPS Code": text_prop(info["fips"]),
        "Population": number_prop(pop),
        "Region": select_prop(info["region"]),
        "Presidential 2024 Winner": select_prop(info["winner_2024"]),
        "Presidential 2024 Margin": number_prop(info["margin_2024"]),
        "Electoral Votes": number_prop(info["ev"]),
        "Swing State": checkbox_prop(abbr in SWING_STATES),
        "Trifecta": select_prop(info["trifecta"]),
        "Right to Work State": checkbox_prop(density.get("right_to_work", False)),
        "Union Density %": number_prop(density.get("overall")),
        "Public Sector Density %": number_prop(density.get("public")),
        "Private Sector Density %": number_prop(density.get("private")),
        "Min Wage": number_prop(density.get("min_wage")),
        "Project Labor Agreement Laws": select_prop(density.get("pla_laws")),
        "Data Quality": select_prop("High"),
    }


def run(config_path: str, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    db_id = config["notion"]["databases"]["states"]
    density_data = json.loads((Path(config_path).parent / "state_union_density.json").read_text())

    if not dry_run:
        client = NotionClient(config["notion"]["api_key"])

    # Fetch population separately to avoid importing task1 at module level
    logger.info("Fetching state populations")
    resp = requests.get(CENSUS_URL, timeout=120)
    resp.raise_for_status()
    content = resp.content.decode("latin-1")
    import io, csv as csv_mod
    reader = csv_mod.DictReader(io.StringIO(content))
    STATE_ABBR_LOCAL = {
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
    state_pops = {}
    for row in reader:
        if row.get("SUMLEV", "").strip() == "040":
            abbr = STATE_ABBR_LOCAL.get(row["STNAME"].strip(), "")
            if abbr:
                state_pops[abbr] = int(row.get("POPESTIMATE2023", 0) or 0)

    ok = 0
    errors = []
    for abbr, info in STATE_DATA.items():
        pop = state_pops.get(abbr, 0)
        density = density_data["states"].get(abbr, {})
        props = build_properties(abbr, info, pop, density)

        if dry_run:
            print(json.dumps({"abbr": abbr, "name": info["name"]}, indent=2))
            ok += 1
            continue
        try:
            client.create_page(db_id, props)
            ok += 1
            logger.info(f"Created {abbr} - {info['name']}")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed {abbr}: {e}")
            errors.append({"abbr": abbr, "error": str(e)})

    logger.info(f"Done. {ok} states created, {len(errors)} errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.config, args.dry_run)
