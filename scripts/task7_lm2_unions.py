"""
Task 7: Build Union Locals Directory from DOL LM-2 Filings
Downloads bulk LM-2 data, parses locals, maps to counties, uploads to UNIONS database.

DOL bulk data: https://www.dol.gov/olms/regs/compliance/ereporting/olmsreporting.htm
Annual ZIP files contain pipe-delimited text files.

Usage:
    python task7_lm2_unions.py --config ../config.json [--year 2023] [--dry-run]
"""

import csv
import io
import json
import logging
import argparse
import time
import zipfile
import tempfile
import os
from pathlib import Path
from typing import Optional

import requests
import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import (
    NotionClient, title_prop, text_prop, number_prop,
    select_prop, checkbox_prop, relation_prop, url_prop
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                               logging.FileHandler("../logs/task7_unions.log")])
logger = logging.getLogger(__name__)

# DOL OLMS Online Public Disclosure Room API
OLMS_FILENAMES_URL = "https://olmsapps.dol.gov/olpdr/GetYearlyDownlaodFilenamesServlet"
OLMS_DOWNLOAD_URL = "https://olmsapps.dol.gov/olpdr/GetYearlyFileServlet"

PARENT_UNION_KEYWORDS = {
    "SEIU": "SEIU", "SERVICE EMPLOYEES": "SEIU",
    "AFSCME": "AFSCME", "AMERICAN FEDERATION OF STATE": "AFSCME",
    "AFT": "AFT", "AMERICAN FEDERATION OF TEACHERS": "AFT",
    "NEA": "NEA", "NATIONAL EDUCATION ASSOCIATION": "NEA",
    "UAW": "UAW", "UNITED AUTO WORKERS": "UAW",
    "TEAMSTERS": "Teamsters", "IBT": "Teamsters",
    "UFCW": "UFCW", "UNITED FOOD": "UFCW",
    "CWA": "CWA", "COMMUNICATIONS WORKERS": "CWA",
    "IBEW": "IBEW", "ELECTRICAL WORKERS": "IBEW",
    "USW": "USW", "STEELWORKERS": "USW",
    "UNITE HERE": "UNITE HERE",
    "LIUNA": "LIUNA", "LABORERS": "LIUNA",
    "IAM": "IAM", "MACHINISTS": "IAM",
    "CNA": "CNA", "CALIFORNIA NURSES": "CNA",
    "NNU": "NNU", "NATIONAL NURSES": "NNU",
    "UE": "UE", "UNITED ELECTRICAL": "UE",
    "APWU": "APWU", "POSTAL WORKERS": "APWU",
    "NALC": "NALC", "LETTER CARRIERS": "NALC",
    "AFGE": "AFGE", "GOVERNMENT EMPLOYEES": "AFGE",
    "NTEU": "NTEU", "TREASURY EMPLOYEES": "NTEU",
}


def detect_parent_union(name: str) -> str:
    name_upper = name.upper()
    for keyword, parent in PARENT_UNION_KEYWORDS.items():
        if keyword in name_upper:
            return parent
    return "Independent/Other"


def city_to_county_lookup() -> dict[tuple[str, str], str]:
    """
    Load or build a city → county FIPS mapping from Census gazetteer data.
    Returns {(city_lower, state_abbr): county_fips}
    """
    lookup_path = Path("../data/city_county_lookup.json")
    if lookup_path.exists():
        return {tuple(k.split("|")): v for k, v in json.loads(lookup_path.read_text()).items()}

    # Try multiple Census gazetteer years in case one mirror is slow
    urls = [
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2022_Gazetteer/2022_Gaz_place_national.zip",
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip",
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2021_Gazetteer/2021_Gaz_place_national.zip",
    ]
    logger.info("Downloading Census place gazetteer for city→county mapping")
    for url in urls:
        try:
            resp = requests.get(url, timeout=180)
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                fname = [n for n in z.namelist() if n.endswith(".txt")][0]
                content = z.read(fname).decode("latin-1")
            reader = csv.DictReader(io.StringIO(content), delimiter="\t")
            lookup = {}
            TYPE_SUFFIXES = (
                " city", " town", " village", " borough", " township", " cdp",
                " municipality", " plantation", " gore", " grant", " location",
                " unorganized", " comunidad", " zona urbana",
            )
            for row in reader:
                raw_name = row.get("NAME", "").lower().strip()
                state = row.get("USPS", "").strip()
                county_fips = row.get("GEOID", "")[:5]
                if not (raw_name and state and county_fips):
                    continue
                # Strip place-type suffix so bare city names match
                bare = raw_name
                for suffix in TYPE_SUFFIXES:
                    if bare.endswith(suffix):
                        bare = bare[:-len(suffix)].strip()
                        break
                for key in (bare, raw_name):
                    full_key = f"{key}|{state}"
                    if full_key not in lookup:
                        lookup[full_key] = county_fips
            lookup_path.write_text(json.dumps(lookup, indent=2))
            logger.info(f"Saved {len(lookup)} city→county mappings")
            return {tuple(k.split("|")): v for k, v in lookup.items()}
        except Exception as e:
            logger.warning(f"City lookup attempt failed ({url}): {e}")
    logger.warning("Could not build city→county lookup; union records will have state relation only")
    return {}


def download_lm2_zip(year: int) -> Optional[bytes]:
    """Fetch the yearly LM data ZIP from the OLMS Online Public Disclosure Room API."""
    # Step 1: get current encrypted filename keys
    try:
        meta = requests.post(OLMS_FILENAMES_URL, timeout=30)
        meta.raise_for_status()
        data = meta.json()
        filenames = data["filenames"]
        encrypted = data["encriptedFilenames"]
    except Exception as e:
        logger.error(f"Could not fetch OLMS filename list: {e}")
        return None

    # Find the requested year; fall back to the most recent available year
    target_year = str(year)
    fallback_year = None
    enc_key = None
    for i, fn in enumerate(filenames):
        if fn == target_year:
            enc_key = encrypted[i]
            break
    if enc_key is None:
        # Use the most recent year that has data (skip 2026+ which may be empty)
        for i, fn in enumerate(filenames):
            y = int(fn) if fn.isdigit() else 0
            if y <= year:
                enc_key = encrypted[i]
                fallback_year = fn
                break
        if enc_key:
            logger.warning(f"Year {year} not found; using {fallback_year} instead")
        else:
            logger.error(f"No usable year found for {year}")
            return None

    # Step 2: download — the server is load-balanced and only some nodes have the file;
    # retry up to 15 times to hit a node that does.
    url = f"{OLMS_DOWNLOAD_URL}?report={enc_key}"
    logger.info(f"Downloading LM yearly data from {url}")
    for attempt in range(1, 16):
        try:
            resp = requests.get(url, timeout=300)
            if resp.status_code == 200 and resp.content[:2] == b"PK":
                logger.info(f"Downloaded {len(resp.content):,} bytes on attempt {attempt}")
                return resp.content
            logger.debug(f"Attempt {attempt}: got non-ZIP response ({len(resp.content)} bytes), retrying…")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Attempt {attempt} failed: {e}")
            time.sleep(2)

    logger.error(f"Could not download LM ZIP after 15 attempts")
    return None


def parse_lm2(zip_bytes: bytes) -> list[dict]:
    unions = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        files = z.namelist()
        logger.info(f"ZIP contains: {files}")

        # Find the main LM data file — prefer *_data_* over *_meta_*
        data_file = next((f for f in files if "lm_data_data" in f.lower()), None)
        if not data_file:
            data_file = next((f for f in files if "lm_data" in f.lower() and "meta" not in f.lower()), None)
        if not data_file:
            data_file = files[0]

        content = z.read(data_file).decode("latin-1", errors="replace")
        # LM-2 files are pipe-delimited
        reader = csv.DictReader(io.StringIO(content), delimiter="|")

        for row in reader:
            form_type = row.get("FORM_TYPE", "").strip()
            # LM-2 is for larger locals; LM-3/4 are smaller — include all
            if form_type and form_type not in ("LM-2", "LM-3", "LM-4", "LM2", "LM3", "LM4"):
                continue

            name = row.get("UNION_NAME", "").strip()
            file_num = str(row.get("F_NUM", "")).strip()
            city = row.get("CITY", "").strip()
            state = row.get("STATE", "").strip()
            members = row.get("MEMBERS", "")

            try:
                member_count = int(float(str(members).replace(",", ""))) if members else 0
            except ValueError:
                member_count = 0

            if not name or not state:
                continue

            unions.append({
                "name": name,
                "file_number": file_num,
                "city": city,
                "state": state,
                "members": member_count,
                "parent_union": detect_parent_union(name),
            })

    logger.info(f"Parsed {len(unions)} union locals from LM-2")
    return unions


def build_properties(union: dict, county_id: Optional[str], state_id: Optional[str]) -> dict:
    props = {
        "Local Name": title_prop(union["name"]),
        "Parent Union": select_prop(union["parent_union"]),
        "LM-2 File Number": text_prop(union["file_number"]),
        "Total Members": number_prop(union["members"] if union["members"] > 0 else None),
        "Multi-County": checkbox_prop(False),
        "Multi-State": checkbox_prop(False),
    }
    if county_id:
        props["Primary County"] = relation_prop([county_id])
    if state_id:
        props["Primary State"] = relation_prop([state_id])
    return props


def run(config_path: str, year: int = 2023, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    notion_cfg = config["notion"]

    county_ids_path = Path("../data/county_ids.json")
    state_ids_path = Path("../data/state_ids.json")

    county_ids: dict[str, str] = json.loads(county_ids_path.read_text()) if county_ids_path.exists() else {}
    state_ids_raw: dict[str, str] = json.loads(state_ids_path.read_text()) if state_ids_path.exists() else {}
    state_ids = {k: v for k, v in state_ids_raw.items() if len(k) == 2}

    city_lookup = city_to_county_lookup()

    if not dry_run:
        client = NotionClient(notion_cfg["api_key"])

    logger.info(f"Downloading LM-2 data for {year}")
    zip_bytes = download_lm2_zip(year)
    if not zip_bytes:
        logger.error("No LM-2 data found; exiting")
        return

    unions = parse_lm2(zip_bytes)

    ok = 0
    unmatched = 0
    errors = []

    for union in unions:
        city_key = (union["city"].lower(), union["state"].upper())
        county_fips = city_lookup.get(city_key)
        county_id = county_ids.get(county_fips) if county_fips else None
        state_id = state_ids.get(union["state"].upper())

        if not county_id:
            unmatched += 1

        props = build_properties(union, county_id, state_id)

        if dry_run:
            if ok < 5:
                print(f"{union['name']} ({union['state']}) → county: {county_fips or 'unknown'}")
            ok += 1
            continue

        try:
            client.create_page(notion_cfg["databases"]["unions"], props)
            ok += 1
            if ok % 500 == 0:
                logger.info(f"Created {ok} union locals")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed {union['name']}: {e}")
            errors.append({"name": union["name"], "error": str(e)})

    logger.info(f"Done. {ok} unions created, {unmatched} county-unmatched, {len(errors)} errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.config, args.year, args.dry_run)
