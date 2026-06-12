"""
Terrain v2.0 — Notion Export for True SLS Formula

Exports sector reach scores and county-sector employment from Notion
to local processed files. Required for true SLS-Capital and SLS-Community
calculation in pipeline/build_v2_scores.py.

Output files:
  data/processed/sector_reach_scores.json
  data/processed/county_sector_employment.json

Usage:
  python scripts/ingest_notion_export.py

Notion databases read:
  SECTORS: 708b403e-4bba-473f-8ebf-84b8d17b5b61
  EMPLOYMENT: a818547b-6f51-4d67-b033-839e638775be
  COUNTIES: ecf094ac-adec-4046-95b6-5d76dafc664e (for FIPS lookup only)
"""

import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from notion_client import NotionClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

def _find_config() -> Path:
    """Find config.json by walking up from the script location."""
    current = Path(__file__).parent
    for _ in range(8):
        candidate = current / "config.json"
        if candidate.exists():
            return candidate
        current = current.parent
    raise FileNotFoundError(f"config.json not found in any parent of {Path(__file__)}")

CONFIG_PATH = _find_config()
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

SECTORS_DB = "708b403e-4bba-473f-8ebf-84b8d17b5b61"
EMPLOYMENT_DB = "a818547b-6f51-4d67-b033-839e638775be"
COUNTIES_DB = "ecf094ac-adec-4046-95b6-5d76dafc664e"


def get_prop(page: dict, prop_name: str, prop_type: str):
    prop = page.get("properties", {}).get(prop_name, {})
    if prop_type == "number":
        return prop.get("number")
    if prop_type == "checkbox":
        return prop.get("checkbox", False)
    if prop_type == "select":
        sel = prop.get("select")
        return sel["name"] if sel else None
    if prop_type == "title":
        lst = prop.get("title", [])
        return lst[0]["text"]["content"] if lst else ""
    if prop_type == "text":
        lst = prop.get("rich_text", [])
        return lst[0]["text"]["content"] if lst else ""
    if prop_type == "relation":
        return [r["id"] for r in prop.get("relation", [])]
    return None


def export_sector_reach_scores(client: NotionClient) -> dict:
    """
    Query Notion SECTORS database and export cap_reach, comm_reach, and
    related ordinal fields. Returns the output dict (also writes to disk).
    """
    logger.info("Loading sectors from Notion SECTORS database...")
    sectors_raw = client.query_all(SECTORS_DB)
    logger.info(f"Fetched {len(sectors_raw)} sector records")

    sectors_out = {}
    for s in sectors_raw:
        sid = s["id"]
        name = get_prop(s, "Sector Name", "title") or ""
        naics = get_prop(s, "NAICS Code", "text") or ""
        cap_reach = get_prop(s, "Cap Crisis Reach", "number")
        comm_reach = get_prop(s, "Comm Crisis Reach", "number")
        comm_facing = get_prop(s, "Community Facing Reach", "number")
        non_off = get_prop(s, "Non-Off Level", "number")
        svs = get_prop(s, "Strategic Value Score", "number")

        cap_reach = int(cap_reach) if cap_reach is not None else 0
        comm_reach = int(comm_reach) if comm_reach is not None else 0
        comm_facing = int(comm_facing) if comm_facing is not None else 0
        non_off = int(non_off) if non_off is not None else 0
        svs = int(svs) if svs is not None else 0

        # dual_crisis_bonus: both cap and comm reach are non-zero
        # whole_worker_bonus: comm reach and community facing are both non-zero
        sectors_out[sid] = {
            "sector_id": sid,
            "sector_name": name,
            "naics": naics,
            "cap_reach": cap_reach,
            "comm_reach": comm_reach,
            "comm_facing": comm_facing,
            "non_off": non_off,
            "svs": svs,
            "dual_crisis_bonus": cap_reach > 0 and comm_reach > 0,
            "whole_worker_bonus": comm_reach > 0 and comm_facing > 0,
        }

    result = {
        "_generated": datetime.now(timezone.utc).isoformat(),
        "_source": "Notion SECTORS database",
        "_database_id": SECTORS_DB,
        "_count": len(sectors_out),
        "sectors": sectors_out,
    }

    out_path = PROCESSED_DIR / "sector_reach_scores.json"
    out_path.write_text(json.dumps(result, indent=2))
    logger.info(f"Wrote sector_reach_scores.json ({len(sectors_out)} sectors)")
    return result


_progress_lock = threading.Lock()
_progress_counter = [0]


def fetch_employment_for_county(
    client: NotionClient, county_uuid: str, fips: str, total: int
) -> tuple:
    """
    Fetch all employment records for one county. Called from worker threads.
    Returns (fips, list_of_emp_records).
    """
    try:
        records = client.query_all(
            EMPLOYMENT_DB,
            {"property": "County", "relation": {"contains": county_uuid}},
        )
    except Exception as e:
        logger.warning(f"Employment query failed for FIPS {fips} ({county_uuid}): {e}")
        records = []

    with _progress_lock:
        _progress_counter[0] += 1
        n = _progress_counter[0]
        if n % 500 == 0:
            logger.info(f"Employment fetch: {n}/{total} counties")

    return (fips, records)


def load_counties(client: NotionClient) -> list:
    """
    Query Notion COUNTIES database. Returns list of (uuid, fips) tuples.
    """
    logger.info("Loading counties from Notion...")
    counties_raw = client.query_all(COUNTIES_DB)
    result = []
    for c in counties_raw:
        fips = get_prop(c, "FIPS Code", "text") or ""
        if fips:
            result.append((c["id"], fips))
    logger.info(f"Loaded {len(result)} counties with FIPS codes")
    return result


def export_county_sector_employment(
    client: NotionClient, counties: list, workers: int = 4
) -> dict:
    """
    Query Notion EMPLOYMENT per county and export employment by county × sector.

    The EMPLOYMENT database times out on unfiltered queries (too large), so we
    query per county using the County relation filter — same pattern as task9_fast.py.
    Uses ThreadPoolExecutor for parallelism.

    Returns the output dict (also writes to disk).
    """
    logger.info(
        f"Fetching employment from Notion EMPLOYMENT database "
        f"({len(counties)} counties, {workers} parallel workers)..."
    )
    logger.info("Expect 15–30 minutes depending on network conditions.")

    _progress_counter[0] = 0
    t0 = time.time()

    employment: dict = {}  # fips -> sector_uuid -> {total_employment, data_source}
    total_records = 0
    skipped_no_sector = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_employment_for_county, client, uuid, fips, len(counties)): fips
            for uuid, fips in counties
        }
        for fut in as_completed(futures):
            fips, records = fut.result()
            if not records:
                continue

            if fips not in employment:
                employment[fips] = {}

            for emp in records:
                sector_ids = get_prop(emp, "Sector", "relation") or []
                total_emp = get_prop(emp, "Total Employment", "number") or 0
                source = get_prop(emp, "Source", "text") or "CBP"

                if not sector_ids:
                    skipped_no_sector += 1
                    continue

                sector_uuid = sector_ids[0]
                total_records += 1

                # Sum across records if multiple exist for same county+sector
                if sector_uuid in employment[fips]:
                    employment[fips][sector_uuid]["total_employment"] += int(total_emp)
                else:
                    employment[fips][sector_uuid] = {
                        "total_employment": int(total_emp),
                        "data_source": source,
                    }

    elapsed = time.time() - t0
    if skipped_no_sector:
        logger.warning(f"Skipped {skipped_no_sector} records with no sector relation")
    logger.info(
        f"Employment fetch complete: {len(employment)} counties, "
        f"{total_records} records (elapsed {elapsed/60:.1f} min)"
    )

    result = {
        "_generated": datetime.now(timezone.utc).isoformat(),
        "_source": "Notion EMPLOYMENT database",
        "_database_id": EMPLOYMENT_DB,
        "_count": total_records,
        "_counties": len(employment),
        "employment": employment,
    }

    out_path = PROCESSED_DIR / "county_sector_employment.json"
    out_path.write_text(json.dumps(result, indent=2))
    logger.info(
        f"Wrote county_sector_employment.json "
        f"({len(employment)} counties, {total_records} records)"
    )
    return result


def validate_and_spot_check(sectors: dict, employment: dict) -> None:
    """Report record counts and spot-check a few counties."""
    sector_data = sectors["sectors"]
    emp_data = employment["employment"]

    logger.info("=== VALIDATION ===")
    logger.info(f"Sectors exported: {sectors['_count']} (expect ~42)")
    logger.info(f"Counties with employment: {employment['_counties']} (expect ~3,144)")
    logger.info(f"Total employment records: {employment['_count']}")

    # Cap/comm reach distribution
    cap_nonzero = sum(1 for s in sector_data.values() if s["cap_reach"] > 0)
    comm_nonzero = sum(1 for s in sector_data.values() if s["comm_reach"] > 0)
    logger.info(f"Sectors with cap_reach > 0: {cap_nonzero}")
    logger.info(f"Sectors with comm_reach > 0: {comm_nonzero}")

    # Spot-check 5 known counties
    spot_fips = ["06037", "17031", "36061", "48201", "53033"]
    for fips in spot_fips:
        county_emp = emp_data.get(fips, {})
        active_sectors = {
            sid: v for sid, v in county_emp.items() if v["total_employment"] > 0
        }
        logger.info(
            f"  County {fips}: {len(active_sectors)} sectors with employment > 0"
        )

    # Manual SLS-Capital spot check for LA County (06037)
    la_fips = "06037"
    la_emp = emp_data.get(la_fips, {})
    if la_emp:
        sls_cap = sum(
            sector_data[sid]["cap_reach"] * v["total_employment"]
            for sid, v in la_emp.items()
            if sid in sector_data
        )
        sls_cap_norm = sls_cap / 1_000_000 if sls_cap else 0
        logger.info(
            f"  LA County (06037) raw SLS-Capital sum: {sls_cap:,.0f} "
            f"(normalized /1M: {sls_cap_norm:.2f})"
        )
    else:
        logger.warning("  LA County (06037) not found in employment data")

    logger.info("=== END VALIDATION ===")


def main():
    config = json.loads(CONFIG_PATH.read_text())
    api_key = config["notion"]["api_key"]

    client = NotionClient(api_key)

    # Smoke test: verify Notion access by fetching one sector
    logger.info("Verifying Notion API access...")
    try:
        test = client.query_database(SECTORS_DB)
        n = len(test.get("results", []))
        logger.info(f"Notion access OK — test query returned {n} results")
    except Exception as e:
        logger.error(f"Notion access FAILED: {e}")
        logger.error("Cannot proceed without Notion access. Exiting.")
        sys.exit(1)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    sectors = export_sector_reach_scores(client)
    counties = load_counties(client)
    employment = export_county_sector_employment(client, counties)
    validate_and_spot_check(sectors, employment)

    logger.info("Export complete.")
    logger.info(f"  {PROCESSED_DIR}/sector_reach_scores.json")
    logger.info(f"  {PROCESSED_DIR}/county_sector_employment.json")


if __name__ == "__main__":
    main()
