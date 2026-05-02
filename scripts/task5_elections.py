"""
Task 5: Collect Presidential Election Results by County
Downloads MIT Election Lab county returns and updates Notion COUNTIES database
with 2020 and 2024 presidential margins.

Usage:
    python task5_elections.py [--config ../config.json] [--dry-run]
"""

import csv
import io
import json
import logging
import argparse
import time
import unicodedata
import re
from pathlib import Path
from typing import Optional

import requests
import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import NotionClient, number_prop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                               logging.FileHandler("../logs/task5_elections.log")])
logger = logging.getLogger(__name__)

GITHUB_2020_URL = "https://raw.githubusercontent.com/tonmcg/US_County_Level_Election_Results_08-24/master/2020_US_County_Level_Presidential_Results.csv"
GITHUB_2024_URL = "https://raw.githubusercontent.com/tonmcg/US_County_Level_Election_Results_08-24/master/2024_US_County_Level_Presidential_Results.csv"

SWING_STATES = {"AZ", "GA", "MI", "NV", "NC", "PA", "WI"}


def normalize_county(name: str) -> str:
    """Lowercase, strip accents, remove 'county'/'parish'/'borough' suffixes."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower().strip()
    name = re.sub(r"\b(county|parish|borough|census area|city and borough|municipality|"
                  r"city|municipio|district|division)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def load_github_results(content: str) -> dict[str, dict]:
    """Parse GitHub county CSV (same format for 2020 and 2024) → {fips: {margin}}"""
    results = {}
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        fips = (row.get("county_fips") or "").zfill(5)
        try:
            dem = float(row.get("votes_dem") or 0)
            rep = float(row.get("votes_gop") or 0)
            total = float(row.get("total_votes") or (dem + rep))
            if total == 0:
                continue
            margin = round((dem - rep) / total * 100, 2)
        except (ValueError, TypeError):
            continue
        if fips and fips != "00000":
            results[fips] = {"margin": margin}
    return results


def load_2024_results(content: str) -> dict[str, dict]:
    """Parse community 2024 CSV → {fips: {margin}}. Column names vary by source."""
    results = {}
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        # Try multiple column name conventions
        fips = (row.get("county_fips") or row.get("fips_code") or row.get("FIPS") or "").zfill(5)
        try:
            dem = float(row.get("votes_dem") or row.get("dem_votes") or 0)
            rep = float(row.get("votes_gop") or row.get("rep_votes") or 0)
            total = float(row.get("total_votes") or row.get("votes_total") or (dem + rep))
            if total == 0:
                continue
            margin = round((dem - rep) / total * 100, 2)
        except (ValueError, TypeError):
            continue
        if fips and fips != "00000":
            results[fips] = {"margin": margin}
    return results


def run(config_path: str, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    notion_cfg = config["notion"]

    county_ids_path = Path("../data/county_ids.json")
    if not county_ids_path.exists():
        logger.error("county_ids.json not found. Run task1 first.")
        return

    county_page_ids: dict[str, str] = json.loads(county_ids_path.read_text())  # fips → page_id

    if not dry_run:
        client = NotionClient(notion_cfg["api_key"])

    # Download election data
    logger.info("Downloading 2020 results from GitHub")
    try:
        resp_2020 = requests.get(GITHUB_2020_URL, timeout=120)
        resp_2020.raise_for_status()
        results_2020 = load_github_results(resp_2020.text)
        logger.info(f"Loaded {len(results_2020)} county 2020 results")
    except Exception as e:
        logger.error(f"Could not download 2020 data: {e}")
        results_2020 = {}

    logger.info("Downloading 2024 results from GitHub")
    try:
        resp_2024 = requests.get(GITHUB_2024_URL, timeout=120)
        resp_2024.raise_for_status()
        results_2024 = load_github_results(resp_2024.text)
        logger.info(f"Loaded {len(results_2024)} county 2024 results")
    except Exception as e:
        logger.error(f"Could not download 2024 data: {e}")
        results_2024 = {}

    ok = 0
    unmatched = []

    for fips, page_id in county_page_ids.items():
        state = fips[:2]
        # 2020 key uses (state_abbr, fips)
        margin_2020 = results_2020.get(fips, {}).get("margin")
        margin_2024 = results_2024.get(fips, {}).get("margin")

        if margin_2020 is None and margin_2024 is None:
            unmatched.append(fips)
            continue

        props: dict = {}
        if margin_2020 is not None:
            props["Presidential 2020 Margin"] = number_prop(margin_2020)
        if margin_2024 is not None:
            props["Presidential 2024 Margin"] = number_prop(margin_2024)
        if state in SWING_STATES:
            props["Swing State"] = {"checkbox": True}

        if dry_run:
            if ok < 5:
                print(f"{fips}: 2020={margin_2020} 2024={margin_2024}")
            ok += 1
            continue

        try:
            client.update_page(page_id, props)
            ok += 1
            if ok % 200 == 0:
                logger.info(f"Updated {ok} counties")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed update {fips}: {e}")

    logger.info(f"Done. {ok} counties updated, {len(unmatched)} unmatched")
    if unmatched:
        Path("../logs/task5_unmatched.json").write_text(json.dumps(unmatched, indent=2))
        logger.warning(f"{len(unmatched)} counties had no election data — see logs/task5_unmatched.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.config, args.dry_run)
