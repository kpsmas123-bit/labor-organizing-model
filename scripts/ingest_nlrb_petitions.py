"""
Task 3: Ingest NLRB R-case (representation) petitions, geocode to county FIPS,
aggregate to county level, write data/nlrb_petitions_by_county.json.

Data source (primary): https://data.nlrb.gov/api/search/case
  - Paginates with ?offset=N&limit=1000
  - Filter: case_type=RC (representation certification)
  - Window: 2022-01-01 through latest available

Geocoding: data/zip_county_map.json (ZIP → FIPS crosswalk)
  - Fallback: 3-digit ZIP prefix → most common county in that prefix group

Output: data/nlrb_petitions_by_county.json
  Schema per county FIPS:
    petition_count_3yr: int
    petition_workers_3yr: int  (sum of eligible_voters)
    most_recent_petition_date: str (ISO)
    petitions: list of raw records

NLRB jurisdiction note: NLRB covers private sector only.
Public sector organizing goes through state labor boards (PERB, MERC, etc.)
and is NOT captured in this data.

Usage:
    python ingest_nlrb_petitions.py [--dry-run] [--limit N]
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("../logs/nlrb_petitions.log"),
    ],
)
logger = logging.getLogger(__name__)

NLRB_BASE = "https://data.nlrb.gov/api/search/case"
WINDOW_START = "2022-01-01"
REQUEST_DELAY = 1.0  # seconds between API calls

NLRB_JURISDICTION_NOTE = (
    "NLRB covers private sector only. Public sector organizing goes through "
    "state labor boards (PERB, MERC, etc.) and is NOT captured here."
)


def load_env() -> str:
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    return os.environ.get("NOTION_API_KEY", "")


def load_zip_county_map() -> dict:
    path = Path(__file__).parent.parent / "data" / "zip_county_map.json"
    with open(path) as f:
        return json.load(f)


def build_prefix_fallback(zip_map: dict) -> dict:
    """3-digit ZIP prefix → most common county FIPS in that group."""
    from collections import Counter
    prefix_counts: dict[str, Counter] = defaultdict(Counter)
    for z, fips in zip_map.items():
        prefix_counts[z[:3]][fips] += 1
    return {prefix: counter.most_common(1)[0][0] for prefix, counter in prefix_counts.items()}


def fetch_petitions(limit_total: int = 0) -> list:
    """Paginate through NLRB API and return all RC petitions since WINDOW_START."""
    all_records = []
    offset = 0
    page_size = 1000
    session = requests.Session()

    while True:
        params = {
            "case_type": "RC",
            "start_date": WINDOW_START,
            "limit": page_size,
            "offset": offset,
        }
        try:
            resp = session.get(NLRB_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error(f"NLRB API request failed at offset={offset}: {e}")
            raise

        # Handle both list and dict response shapes
        if isinstance(data, list):
            records = data
            total_hint = None
        elif isinstance(data, dict):
            # Common shapes: {"results": [...], "count": N} or {"hits": [...]}
            records = (
                data.get("results")
                or data.get("hits")
                or data.get("cases")
                or data.get("data")
                or []
            )
            total_hint = data.get("count") or data.get("total")
        else:
            logger.error(f"Unexpected API response shape: {type(data)}")
            break

        if not records:
            logger.info(f"No more records at offset={offset}")
            break

        all_records.extend(records)
        logger.info(
            f"Fetched {len(records)} records at offset={offset} "
            f"(total so far: {len(all_records)}"
            + (f", total available: {total_hint}" if total_hint else "")
            + ")"
        )

        if limit_total and len(all_records) >= limit_total:
            logger.info(f"Reached --limit {limit_total}, stopping early")
            break

        if len(records) < page_size:
            break  # last page

        offset += page_size
        time.sleep(REQUEST_DELAY)

    logger.info(f"Total RC petitions fetched: {len(all_records)}")
    return all_records


def normalize_record(raw: dict) -> dict:
    """Extract the fields we care about from a raw API record (handles multiple shapes)."""
    # Field name variations observed in NLRB API
    def get(*keys):
        for k in keys:
            v = raw.get(k)
            if v is not None:
                return v
        return None

    return {
        "case_number": get("case_number", "case_id", "id"),
        "date_filed":  get("date_filed", "filed_date", "filing_date"),
        "employer_name": get("employer_name", "employer", "respondent_name"),
        "employer_city": get("employer_city", "city"),
        "employer_state": get("employer_state", "state"),
        "employer_zip":  get("employer_zip", "zip", "zip_code", "postal_code"),
        "naics_code":    get("industry_code", "naics_code", "naics"),
        "eligible_voters": get("eligible_voters", "unit_size", "employees_covered", "employees"),
    }


def geocode_zip(zip_raw: str, zip_map: dict, prefix_map: dict,
                unmatched_log: list) -> str:
    """Return 5-digit county FIPS or empty string."""
    if not zip_raw:
        return ""
    z = str(zip_raw).strip().split("-")[0].zfill(5)  # handle ZIP+4, pad short ZIPs
    if z in zip_map:
        return zip_map[z]
    prefix = z[:3]
    if prefix in prefix_map:
        unmatched_log.append(f"ZIP {z} → prefix fallback → {prefix_map[prefix]}")
        return prefix_map[prefix]
    unmatched_log.append(f"ZIP {z} → no match")
    return ""


def aggregate(records: list, zip_map: dict, prefix_map: dict) -> tuple:
    """
    Returns (county_data dict, unmatched_zips list).
    county_data keys: FIPS strings
    """
    county_data: dict[str, dict] = {}
    unmatched: list[str] = []
    skipped_no_zip = 0

    for raw in records:
        r = normalize_record(raw)
        fips = geocode_zip(r["employer_zip"] or "", zip_map, prefix_map, unmatched)
        if not fips:
            skipped_no_zip += 1
            continue

        if fips not in county_data:
            county_data[fips] = {
                "petition_count_3yr": 0,
                "petition_workers_3yr": 0,
                "most_recent_petition_date": "",
                "petitions": [],
            }

        entry = county_data[fips]
        entry["petition_count_3yr"] += 1

        workers = r["eligible_voters"]
        if workers is not None:
            try:
                entry["petition_workers_3yr"] += int(workers)
            except (ValueError, TypeError):
                pass

        date_str = r["date_filed"] or ""
        if date_str and date_str > entry["most_recent_petition_date"]:
            entry["most_recent_petition_date"] = date_str[:10]  # keep ISO date portion

        entry["petitions"].append(r)

    logger.info(f"Geocoded to {len(county_data)} counties. "
                f"Skipped (no ZIP match): {skipped_no_zip}. "
                f"Unmatched ZIPs: {len(unmatched)}.")
    return county_data, unmatched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Fetch and aggregate but don't write output file")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N petitions (for testing)")
    args = parser.parse_args()

    load_env()

    logger.info("=== NLRB Petition Ingest ===")
    logger.info(f"Window: {WINDOW_START} → present")
    logger.info(f"Jurisdiction note: {NLRB_JURISDICTION_NOTE}")

    # Load crosswalk data
    zip_map = load_zip_county_map()
    prefix_map = build_prefix_fallback(zip_map)
    logger.info(f"ZIP→county map loaded: {len(zip_map):,} entries, {len(prefix_map)} prefix fallbacks")

    # Fetch petitions
    try:
        records = fetch_petitions(limit_total=args.limit)
    except Exception as e:
        logger.error(f"Failed to fetch NLRB data: {e}")
        logger.error("Primary API failed. Stopping — do not scrape nlrb.gov without approval.")
        sys.exit(1)

    if not records:
        logger.error("No petitions returned. Check API availability.")
        sys.exit(1)

    # Aggregate to county level
    county_data, unmatched_zips = aggregate(records, zip_map, prefix_map)

    # Write unmatched ZIP log
    unmatched_log_path = Path("../logs/nlrb_unmatched_zips.log")
    with open(unmatched_log_path, "w") as f:
        f.write(f"# NLRB unmatched ZIPs — {datetime.now().isoformat()}\n")
        f.write(f"# Total: {len(unmatched_zips)}\n")
        for line in unmatched_zips:
            f.write(line + "\n")
    logger.info(f"Unmatched ZIPs written to {unmatched_log_path}")

    # Build output structure
    output = {
        "_meta": {
            "generated": datetime.now().isoformat(),
            "window_start": WINDOW_START,
            "total_petitions": len(records),
            "counties_with_petitions": len(county_data),
            "nlrb_jurisdiction_note": NLRB_JURISDICTION_NOTE,
        }
    }
    output.update(county_data)

    # Top 10 report
    top10 = sorted(county_data.items(), key=lambda x: x[1]["petition_count_3yr"], reverse=True)[:10]
    logger.info("=== Top 10 counties by RC petition count (2022–present) ===")
    for fips, d in top10:
        logger.info(
            f"  {fips}  count={d['petition_count_3yr']:>4}  "
            f"workers={d['petition_workers_3yr']:>6}  "
            f"latest={d['most_recent_petition_date']}"
        )

    # PA sample (state FIPS 42)
    pa_counties = {k: v for k, v in county_data.items() if k.startswith("42")}
    pa_top = sorted(pa_counties.items(), key=lambda x: x[1]["petition_count_3yr"], reverse=True)[:5]
    logger.info(f"=== PA sample — {len(pa_counties)} PA counties with petitions ===")
    for fips, d in pa_top:
        logger.info(
            f"  {fips}  count={d['petition_count_3yr']:>3}  "
            f"workers={d['petition_workers_3yr']:>5}  "
            f"latest={d['most_recent_petition_date']}"
        )

    if args.dry_run:
        logger.info("--dry-run: output file not written")
        return

    # Write output
    out_path = Path(__file__).parent.parent / "data" / "nlrb_petitions_by_county.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    logger.info(f"Written: {out_path}  ({out_path.stat().st_size:,} bytes)")
    logger.info("=== Done. Stop here — report to Sam before any scoring changes. ===")


if __name__ == "__main__":
    main()
