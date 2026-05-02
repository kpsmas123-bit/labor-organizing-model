"""
Helper: Export Notion page IDs for each database record so downstream scripts
can build relations without re-fetching.

Run after each Task 1-3 to produce:
  data/county_ids.json   {fips_code: page_id}
  data/state_ids.json    {state_abbr: page_id}
  data/sector_ids.json   {naics_code: page_id}
  data/union_name_ids.json {local_name_lower: page_id}

Usage:
    python export_page_ids.py --config ../config.json --db counties
    python export_page_ids.py --config ../config.json --db states
    python export_page_ids.py --config ../config.json --db sectors
    python export_page_ids.py --config ../config.json --db unions
"""

import json
import logging
import argparse
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import NotionClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

Path("../data").mkdir(parents=True, exist_ok=True)


def get_text(page: dict, prop: str) -> str:
    p = page["properties"].get(prop, {})
    for key in ("title", "rich_text"):
        lst = p.get(key, [])
        if lst:
            return lst[0].get("text", {}).get("content", "").strip()
    sel = p.get("select")
    if sel:
        return sel.get("name", "")
    return ""


def export_counties(client: NotionClient, db_id: str):
    logger.info("Exporting county FIPS → page_id")
    pages = client.query_all(db_id)
    mapping = {}
    for page in pages:
        fips = get_text(page, "FIPS Code")
        if fips:
            mapping[fips] = page["id"]
    out = Path("../data/county_ids.json")
    out.write_text(json.dumps(mapping, indent=2))
    logger.info(f"Saved {len(mapping)} county IDs to {out}")


def export_states(client: NotionClient, db_id: str):
    logger.info("Exporting state abbr → page_id")
    pages = client.query_all(db_id)
    mapping = {}
    for page in pages:
        abbr = get_text(page, "State Abbr")
        if abbr:
            mapping[abbr] = page["id"]
    out = Path("../data/state_ids.json")
    out.write_text(json.dumps(mapping, indent=2))
    logger.info(f"Saved {len(mapping)} state IDs to {out}")


def export_sectors(client: NotionClient, db_id: str):
    logger.info("Exporting NAICS code → page_id")
    pages = client.query_all(db_id)
    mapping = {}
    for page in pages:
        naics = get_text(page, "NAICS Code")
        if naics:
            mapping[naics] = page["id"]
    out = Path("../data/sector_ids.json")
    out.write_text(json.dumps(mapping, indent=2))
    logger.info(f"Saved {len(mapping)} sector IDs to {out}")


def export_unions(client: NotionClient, db_id: str):
    logger.info("Exporting union name (lowercase) → page_id")
    pages = client.query_all(db_id)
    mapping = {}
    for page in pages:
        name = get_text(page, "Local Name").lower()
        if name:
            mapping[name] = page["id"]
    out = Path("../data/union_name_ids.json")
    out.write_text(json.dumps(mapping, indent=2))
    logger.info(f"Saved {len(mapping)} union IDs to {out}")


def run(config_path: str, db: str):
    config = json.loads(Path(config_path).read_text())
    client = NotionClient(config["notion"]["api_key"])
    db_id = config["notion"]["databases"][db]

    dispatch = {
        "counties": export_counties,
        "states": export_states,
        "sectors": export_sectors,
        "unions": export_unions,
    }
    if db not in dispatch:
        logger.error(f"Unknown db '{db}'. Choose from: {list(dispatch)}")
        return
    dispatch[db](client, db_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--db", required=True,
                        choices=["counties", "states", "sectors", "unions"])
    args = parser.parse_args()
    run(args.config, args.db)
