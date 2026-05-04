"""
Enrich county_scores.json with CBSA (MSA) names and codes.

Downloads the Census Bureau CBSA delineation file, maps each county FIPS
to its Metropolitan/Micropolitan Statistical Area, and writes the enriched
data back to county_scores.json.

Counties not in any CBSA get msa_code=None, msa_name="Non-Metro",
msa_type="Non-Metro".

Usage:
    python enrich_msa.py [--scores ../data/county_scores.json]
"""

import csv, io, json, logging, zipfile
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Census CBSA delineation file — county-to-CBSA crosswalk
# Updated annually; this is the March 2023 delineation (stable for 2024 cycle)
CBSA_URL = (
    "https://www2.census.gov/programs-surveys/metro-micro/geographies/"
    "reference-files/2023/delineation-files/list1_2023.xlsx"
)


def fetch_cbsa_crosswalk() -> dict[str, dict]:
    """
    Returns {county_fips_5: {msa_code, msa_name, msa_type}} by downloading
    the Census CBSA delineation XLS and parsing it with openpyxl, or falling
    back to a known-stable CSV mirror if openpyxl isn't available.
    """
    # Try openpyxl path first (parses the official Census XLS)
    try:
        import openpyxl
        return _fetch_via_openpyxl()
    except ImportError:
        logger.warning("openpyxl not installed — trying CSV fallback")

    # CSV fallback: OMB publishes a pipe-delimited version via data.census.gov
    return _fetch_via_csv_fallback()


def _fetch_via_openpyxl() -> dict[str, dict]:
    import openpyxl
    logger.info("Downloading Census CBSA delineation XLS")
    resp = requests.get(CBSA_URL, timeout=120)
    resp.raise_for_status()

    wb = openpyxl.load_workbook(io.BytesIO(resp.content), read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    # Row 3 is the header in the Census XLS; rows 1-2 are title/blank
    header = [str(c).strip() if c else "" for c in rows[2]]

    def col(name):
        for i, h in enumerate(header):
            if name.lower() in h.lower():
                return i
        return None

    cbsa_col    = col("CBSA Code")
    title_col   = col("CBSA Title")
    type_col    = col("Metropolitan/Micropolitan")
    state_col   = col("FIPS State Code")
    county_col  = col("FIPS County Code")

    result = {}
    for row in rows[3:]:
        if not row or not row[cbsa_col]:
            continue
        cbsa_code  = str(row[cbsa_col]).strip().zfill(5)
        cbsa_title = str(row[title_col]).strip() if row[title_col] else ""
        cbsa_type  = str(row[type_col]).strip() if row[type_col] else ""
        state_fips = str(row[state_col]).strip().zfill(2) if row[state_col] else ""
        county_fips_3 = str(row[county_col]).strip().zfill(3) if row[county_col] else ""
        if state_fips and county_fips_3:
            fips5 = state_fips + county_fips_3
            result[fips5] = {
                "msa_code": cbsa_code,
                "msa_name": cbsa_title,
                "msa_type": "Metro" if "Metropolitan" in cbsa_type else "Micro",
            }

    logger.info(f"Loaded {len(result)} county→CBSA mappings from XLS")
    return result


def _fetch_via_csv_fallback() -> dict[str, dict]:
    """
    Use the HUD USPS ZIP-CBSA crosswalk or a known static CSV.
    Falls back to a publicly available reformatted version of the Census file.
    """
    # Simplified CSV published by the Missouri Census Data Center
    # and mirrored by several academic institutions
    CSV_MIRROR = (
        "https://raw.githubusercontent.com/Census-Bureau/cbsa-delineation/"
        "main/list1_2023.csv"
    )
    # Most reliable fallback: build from the OMB bulletin appendix
    # which is consistently available as a text table
    BACKUP_URL = (
        "https://www.whitehouse.gov/wp-content/uploads/2023/07/"
        "Bulletin-23-01-Appendix.xlsx"
    )

    # Try a known-good reformatted CSV (hosted by academic institutions)
    known_csvs = [
        "https://data.nber.org/cbsa-msa-fips-ssa-county-crosswalk/cbsatocountycrosswalk.csv",
    ]

    for url in known_csvs:
        try:
            logger.info(f"Trying CSV fallback: {url}")
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            reader = csv.DictReader(io.StringIO(resp.text))
            result = {}
            for row in reader:
                fips = (row.get("fipscounty") or row.get("FIPS") or "").strip().zfill(5)
                cbsa = (row.get("cbsa") or row.get("CBSA") or "").strip().zfill(5)
                name = (row.get("cbsaname") or row.get("MSA_NAME") or "").strip()
                if fips and cbsa and cbsa != "00000":
                    result[fips] = {
                        "msa_code": cbsa,
                        "msa_name": name,
                        "msa_type": "Metro",  # NBER file only has metros
                    }
            if result:
                logger.info(f"Loaded {len(result)} county→CBSA mappings from CSV fallback")
                return result
        except Exception as e:
            logger.warning(f"CSV fallback failed ({url}): {e}")

    logger.error("Could not load CBSA data from any source")
    return {}


def run(scores_path: str = "../data/county_scores.json"):
    path = Path(scores_path)
    scores = json.loads(path.read_text())

    cbsa_map = fetch_cbsa_crosswalk()

    if not cbsa_map:
        logger.error("No CBSA data loaded — aborting")
        return

    matched = 0
    for county in scores:
        fips = county.get("fips", "").zfill(5)
        cbsa = cbsa_map.get(fips)
        if cbsa:
            county["msa_code"] = cbsa["msa_code"]
            county["msa_name"] = cbsa["msa_name"]
            county["msa_type"] = cbsa["msa_type"]
            matched += 1
        else:
            county["msa_code"] = None
            county["msa_name"] = "Non-Metro"
            county["msa_type"] = "Non-Metro"

    path.write_text(json.dumps(scores, indent=2))

    total = len(scores)
    logger.info(f"Enriched {matched}/{total} counties with CBSA data ({100*matched/total:.1f}% in an MSA)")
    logger.info(f"{total - matched} counties marked Non-Metro")

    # Summary of top MSAs by county count
    from collections import Counter
    msa_counts = Counter(c["msa_name"] for c in scores if c.get("msa_name") != "Non-Metro")
    logger.info("Top 10 MSAs by county count:")
    for name, n in msa_counts.most_common(10):
        logger.info(f"  {name}: {n} counties")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--scores", default="../data/county_scores.json")
    args = p.parse_args()
    run(args.scores)
