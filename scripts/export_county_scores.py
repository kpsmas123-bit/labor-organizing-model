# FROZEN: Do not edit. v2.0 parallel build in progress. See MASTER_PLAN.md
"""
Export all scored county data from Notion to data/county_scores.json
so the dashboard can load it without hitting the Notion API on every open.

Run this after task9_score_counties.py completes.

Usage:
    python export_county_scores.py --config ../config.json
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


def get_text(page, prop):
    p = page["properties"].get(prop, {})
    for key in ("title", "rich_text"):
        lst = p.get(key, [])
        if lst:
            return lst[0].get("text", {}).get("content", "").strip()
    sel = p.get("select")
    return sel["name"] if sel else ""


def get_num(page, prop):
    return page["properties"].get(prop, {}).get("number")


def get_bool(page, prop):
    return page["properties"].get(prop, {}).get("checkbox", False)


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

SWING_STATES = {"AZ", "GA", "MI", "NV", "NC", "PA", "WI"}


def run(config_path: str):
    config = json.loads(Path(config_path).read_text())
    client = NotionClient(config["notion"]["api_key"])
    db_id = config["notion"]["databases"]["counties"]

    logger.info("Fetching all counties from Notion…")
    pages = client.query_all(db_id)
    logger.info(f"Fetched {len(pages)} counties")

    records = []
    for page in pages:
        fips = get_text(page, "FIPS Code")
        state = FIPS_TO_STATE.get(fips[:2], "") if fips else ""
        records.append({
            "id": page["id"],
            "fips": fips,
            "county_name": get_text(page, "County Name"),
            "state": state,
            "region": get_text(page, "Region"),
            "population": get_num(page, "Population"),
            "rural_urban": get_text(page, "Rural/Urban"),
            "swing_state": state in SWING_STATES,
            "margin_2024": get_num(page, "Presidential 2024 Margin"),
            "margin_2020": get_num(page, "Presidential 2020 Margin"),
            # Primary outputs
            "organizing_opportunity_score": get_num(page, "Organizing Opportunity Score"),
            "intervention_type": get_text(page, "Intervention Type"),
            # Electoral sub-scores
            "presidential_score": get_num(page, "Presidential Score"),
            "statewide_score": get_num(page, "Statewide Score"),
            "congressional_score": get_num(page, "Congressional Score"),
            "electoral_score": get_num(page, "Electoral Geography Score"),
            # Organizing
            "organizing_score": get_num(page, "Organizing Potential Score"),
            "sectoral_score": get_num(page, "Sectoral Value Score"),
            # Infrastructure sub-scores
            "organized_scale_score": get_num(page, "Organized Scale Score"),
            "union_culture_score": get_num(page, "Union Culture Score"),
            "infra_score": get_num(page, "Infrastructure Score"),
            # Reference
            "terrain_score": get_num(page, "Strategic Terrain Score"),
            "priority_tier": get_text(page, "Priority Tier"),
        })

    out = Path(config_path).parent / "data" / "county_scores.json"
    out.write_text(json.dumps(records, indent=2))
    logger.info(f"Saved {len(records)} counties to {out}")

    # Quick validation
    scored = [r for r in records if r["organizing_opportunity_score"] is not None]
    no_intervention = [r for r in records if not r["intervention_type"]]
    tier_a = [r for r in records if (r["priority_tier"] or "").startswith("A")]
    tier_b = [r for r in records if (r["priority_tier"] or "").startswith("B")]
    tier_c = [r for r in records if (r["priority_tier"] or "").startswith("C")]
    logger.info(f"Scored: {len(scored)} | Missing intervention_type: {len(no_intervention)}")
    logger.info(f"Tier A={len(tier_a)} B={len(tier_b)} C={len(tier_c)}")

    # Top 20 by OPP
    top20 = sorted(scored, key=lambda r: r["organizing_opportunity_score"] or 0, reverse=True)[:20]
    print("\nTop 20 counties by Organizing Opportunity Score:")
    for i, r in enumerate(top20, 1):
        print(f"  {i:2}. {r['fips']} {r['county_name']}, {r['state']} "
              f"OPP={r['organizing_opportunity_score']} pres={r['presidential_score']} [{r['intervention_type']}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    args = parser.parse_args()
    run(args.config)
