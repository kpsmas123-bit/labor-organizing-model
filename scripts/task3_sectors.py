"""
Task 3 (pre-BLS): Seed the SECTORS database from naics_sectors.json.
Run this before employment data collection so relations can be established.

Usage:
    python task3_sectors.py [--config /path/to/config.json] [--dry-run]
"""

import json
import logging
import argparse
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import (
    NotionClient, title_prop, text_prop, number_prop,
    select_prop, checkbox_prop
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                               logging.FileHandler("../logs/task3_sectors.log")])
logger = logging.getLogger(__name__)


def strategic_value_score(sector: dict) -> int:
    score = 0
    if sector.get("non_offshoreable"): score += 30
    if sector.get("crisis_creating"):  score += 30
    if sector.get("community_facing"): score += 25
    if sector.get("chokepoint_potential"): score += 15
    return score


def build_properties(sector: dict) -> dict:
    sv = strategic_value_score(sector)
    return {
        "Sector Name": title_prop(sector["name"]),
        "NAICS Code": text_prop(sector["naics"]),
        "Sector Type": select_prop(sector["sector_type"]),
        "Non-Offshoreable": checkbox_prop(sector.get("non_offshoreable", False)),
        "Crisis-Creating": checkbox_prop(sector.get("crisis_creating", False)),
        "Community-Facing": checkbox_prop(sector.get("community_facing", False)),
        "Chokepoint Potential": checkbox_prop(sector.get("chokepoint_potential", False)),
        "Strategic Value Score": number_prop(sv),
        "US Total Employment": number_prop(sector.get("us_employment_est")),
        "Avg Union Density %": number_prop(sector.get("avg_union_density")),
        "Organizability": select_prop(sector.get("organizability", "Medium")),
        "McAlevey Priority": checkbox_prop(sector.get("mcalevey_priority", False)),
        "Description": {
            "rich_text": [{"text": {"content": sector.get("description", "")[:2000]}}]
        },
    }


def run(config_path: str, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    db_id = config["notion"]["databases"]["sectors"]
    sectors_data = json.loads((Path(config_path).parent / "naics_sectors.json").read_text())

    if not dry_run:
        client = NotionClient(config["notion"]["api_key"])

    created_ids = {}  # name -> notion page_id (for export/use by later scripts)
    ok = 0
    errors = []
    for sector in sectors_data["sectors"]:
        props = build_properties(sector)
        if dry_run:
            print(f"{sector['name']} → Strategic Value: {strategic_value_score(sector)}")
            ok += 1
            continue
        try:
            result = client.create_page(db_id, props)
            created_ids[sector["name"]] = result["id"]
            ok += 1
            logger.info(f"Created sector: {sector['name']}")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed {sector['name']}: {e}")
            errors.append({"name": sector["name"], "error": str(e)})

    if not dry_run:
        # Save sector IDs for later scripts to use
        out = Path("../data/sector_ids.json")
        out.write_text(json.dumps(created_ids, indent=2))
        logger.info(f"Saved {len(created_ids)} sector IDs to {out}")

    logger.info(f"Done. {ok} sectors created, {len(errors)} errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.config, args.dry_run)
