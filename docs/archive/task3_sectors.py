# FROZEN: Do not edit. v2.0 parallel build in progress. See MASTER_PLAN.md
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


def calc_score_v6(cap: int, comm: int, facing: int, non_off: int) -> int:
    REACH   = {0: 0, 1: 10, 2: 15, 3: 25}
    FACING  = {0: 0, 1: 5,  2: 10, 3: 15}
    NON_OFF = {0: 0, 1: 3,  2: 5}
    score = REACH[cap] + REACH[comm] + FACING[facing] + NON_OFF[non_off]
    if cap > 0 and comm > 0:
        score += 5   # dual_crisis bonus
    if comm > 0 and facing > 0:
        score += 5   # whole_worker bonus
    return score


def build_properties(sector: dict) -> dict:
    sv = calc_score_v6(
        sector["cap_crisis_reach"],
        sector["community_crisis_reach"],
        sector["community_facing_reach"],
        sector["non_off_level"],
    )
    return {
        "Sector Name":             title_prop(sector["name"]),
        "Sector ID":               text_prop(sector["id"]),
        "NAICS Code":              text_prop(", ".join(sector["naics"])),
        "Data Source":             text_prop(sector["data_source"]),
        "Cap Crisis Reach":        number_prop(sector["cap_crisis_reach"]),
        "Cap Crisis Label":        text_prop(sector["cap_crisis_label"]),
        "Comm Crisis Reach":       number_prop(sector["community_crisis_reach"]),
        "Comm Crisis Label":       text_prop(sector["community_crisis_label"]),
        "Community Facing Reach":  number_prop(sector["community_facing_reach"]),
        "Community Facing Label":  text_prop(sector["community_facing_label"]),
        "Non-Off Level":           number_prop(sector["non_off_level"]),
        "Non-Off Label":           text_prop(sector["non_off_label"]),
        "Notation":                text_prop(sector.get("notation") or ""),
        "Strategic Value Score":   number_prop(sv),
    }


def run(config_path: str, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    db_id = config["notion"]["databases"]["sectors"]
    sectors_data = json.loads((Path(config_path).parent / "naics_sectors.json").read_text())

    if not dry_run:
        client = NotionClient(config["notion"]["api_key"])

    created_ids = {}  # v6 sector id ("01", "07a") -> notion page_id
    ok = 0
    errors = []
    for sector in sectors_data["sectors"]:
        sv = calc_score_v6(
            sector["cap_crisis_reach"],
            sector["community_crisis_reach"],
            sector["community_facing_reach"],
            sector["non_off_level"],
        )
        if dry_run:
            spec_sv = sector.get("svs")
            match = "✓" if sv == spec_sv else f"✗ (spec={spec_sv})"
            print(f"{sector['id']:5s}  {sector['name']:<35s}  SVS={sv:3d}  {match}")
            ok += 1
            continue
        props = build_properties(sector)
        try:
            result = client.create_page(db_id, props)
            created_ids[sector["id"]] = result["id"]
            ok += 1
            logger.info(f"Created sector: {sector['id']} {sector['name']}")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed {sector['id']} {sector['name']}: {e}")
            errors.append({"id": sector["id"], "name": sector["name"], "error": str(e)})

    if not dry_run:
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
