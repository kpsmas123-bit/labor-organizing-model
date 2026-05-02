"""
Task 6: Update STATES with union density from state_union_density.json
and propagate estimated union members to EMPLOYMENT records.

This runs in two passes:
  Pass 1: Update STATES table with density/RTW/min-wage data
  Pass 2: Update each EMPLOYMENT record with estimated union members

Usage:
    python task6_union_density.py --config ../config.json [--pass 1|2] [--dry-run]
"""

import json
import logging
import argparse
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import NotionClient, number_prop, select_prop, checkbox_prop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                               logging.FileHandler("../logs/task6_density.log")])
logger = logging.getLogger(__name__)

PUBLIC_NAICS = {"9211", "9221", "9231", "921", "922", "923", "924"}
EDUCATION_NAICS = {"6111", "6112", "6113", "611"}


def density_for_naics(naics: str, state_density: dict) -> tuple[float, str]:
    """Return (rate_pct, confidence) for a given NAICS code in this state."""
    if naics in PUBLIC_NAICS or naics.startswith("92"):
        return state_density.get("public", state_density.get("overall", 10.0)), "Medium"
    if naics in EDUCATION_NAICS or naics.startswith("61"):
        # Education tends higher than overall private; use blended estimate
        priv = state_density.get("private", 5.0)
        pub = state_density.get("public", 30.0)
        edu_est = min(pub, priv * 4)  # rough education premium
        return round(edu_est, 1), "Medium"
    return state_density.get("private", state_density.get("overall", 5.0)), "Medium"


def pass1_update_states(config: dict, density_data: dict, state_ids: dict[str, str],
                        client, dry_run: bool):
    """Update each state page with RTW, density, min-wage fields."""
    ok = 0
    for abbr, page_id in state_ids.items():
        d = density_data["states"].get(abbr)
        if not d:
            continue
        props = {
            "Union Density %": number_prop(d.get("overall")),
            "Public Sector Density %": number_prop(d.get("public")),
            "Private Sector Density %": number_prop(d.get("private")),
            "Right to Work State": checkbox_prop(d.get("right_to_work", False)),
            "Min Wage": number_prop(d.get("min_wage")),
            "Project Labor Agreement Laws": select_prop(d.get("pla_laws", "Neutral")),
            "Data Quality": select_prop("High"),
        }
        if dry_run:
            logger.info(f"[DRY] {abbr}: density={d.get('overall')}% RTW={d.get('right_to_work')}")
            ok += 1
            continue
        try:
            client.update_page(page_id, props)
            ok += 1
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed {abbr}: {e}")
    logger.info(f"Pass 1: Updated {ok} states")


def pass2_update_employment(config: dict, density_data: dict, state_fips_to_abbr: dict,
                            client, dry_run: bool):
    """
    For every EMPLOYMENT record without union density, set Estimated Union Members and
    Est Union Density. Filters to only unprocessed records so re-runs are safe.
    """
    if dry_run:
        logger.info("[DRY] Pass 2 would update all unprocessed EMPLOYMENT records with union estimates")
        return

    emp_db = config["notion"]["databases"]["employment"]
    # Only fetch records that haven't been processed yet — safe to re-run
    unprocessed_filter = {
        "property": "Est. Union Density %",
        "number": {"is_empty": True}
    }
    records = client.query_all(emp_db, unprocessed_filter)
    logger.info(f"Pass 2: {len(records)} unprocessed employment records to update")

    ok = 0
    for rec in records:
        props_in = rec.get("properties", {})

        # Extract employment count
        emp = props_in.get("Total Employment", {}).get("number") or 0
        if emp == 0:
            continue

        # Extract NAICS via Record ID (format: FIPS-NAICS)
        record_id_list = props_in.get("Record ID", {}).get("title", [])
        record_id = record_id_list[0]["text"]["content"] if record_id_list else ""
        parts = record_id.split("-")
        fips = parts[0] if parts else ""
        naics = parts[1] if len(parts) > 1 else ""

        state_abbr = state_fips_to_abbr.get(fips[:2], "")
        state_density = density_data["states"].get(state_abbr, {})
        if not state_density:
            continue

        rate, confidence = density_for_naics(naics, state_density)
        est_members = round(emp * rate / 100)

        update_props = {
            "Estimated Union Members": number_prop(est_members),
            "Est. Union Density %": number_prop(rate),
            "Density Source": select_prop("State Average"),
            "Confidence": select_prop(confidence),
        }
        try:
            client.update_page(rec["id"], update_props)
            ok += 1
            if ok % 500 == 0:
                logger.info(f"Updated {ok}/{len(records)} unprocessed records")
            time.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed {record_id}: {e}")

    logger.info(f"Pass 2: Updated {ok} employment records")


def run(config_path: str, which_pass: int, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    density_data = json.loads((Path(config_path).parent / "state_union_density.json").read_text())

    state_ids_path = Path("../data/state_ids.json")
    if not state_ids_path.exists():
        logger.error("state_ids.json not found. Need state Notion page IDs.")
        return

    # state_ids.json: abbr → page_id AND state_fips → abbr for employment lookup
    raw = json.loads(state_ids_path.read_text())
    # Support both {abbr: id} and {fips: abbr} in same file
    state_ids = {k: v for k, v in raw.items() if len(k) == 2 and not k.isdigit()}

    # Build fips→abbr from STATE_DATA in task2
    STATE_FIPS = {
        "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
        "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
        "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
        "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
        "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
        "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
        "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
        "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
        "54": "WV", "55": "WI", "56": "WY",
    }

    client = None if dry_run else NotionClient(config["notion"]["api_key"])

    if which_pass in (1, 0):
        pass1_update_states(config, density_data, state_ids, client, dry_run)
    if which_pass in (2, 0):
        pass2_update_employment(config, density_data, STATE_FIPS, client, dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--pass", dest="which_pass", type=int, default=0,
                        choices=[0, 1, 2],
                        help="0=both, 1=states only, 2=employment only")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.config, args.which_pass, args.dry_run)
