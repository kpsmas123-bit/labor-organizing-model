"""
Backfill Primary County relation on UNIONS records that have no county set.

Strategy:
  1. Re-download LM 2022 data → build {F_NUM: ZIP} mapping
  2. Download Census ZCTA-to-county crosswalk → build {zip: county_fips}
     (for multi-county ZIPs, pick the county with the largest residential ratio)
  3. Query all UNIONS records where Primary County is empty
  4. For each, match LM-2 File Number → ZIP → county FIPS → Notion page_id
  5. PATCH Primary County on matched records

Run once after task7_lm2_unions.py completes.
"""

import csv, io, json, logging, time, zipfile
from pathlib import Path
from typing import Optional

import requests, sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import NotionClient, relation_prop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(),
                               logging.FileHandler("../logs/fix_union_backfill.log")])
logger = logging.getLogger(__name__)

OLMS_FILENAMES_URL = "https://olmsapps.dol.gov/olpdr/GetYearlyDownlaodFilenamesServlet"
OLMS_DOWNLOAD_URL  = "https://olmsapps.dol.gov/olpdr/GetYearlyFileServlet"

ZCTA_COUNTY_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
    "tab20_zcta520_county20_natl.txt"
)


# ── Step 1: LM data → {file_num: zip} ─────────────────────────────────────

def get_enc_key(year: int) -> Optional[str]:
    meta = requests.post(OLMS_FILENAMES_URL, timeout=30)
    meta.raise_for_status()
    data = meta.json()
    filenames = data["filenames"]
    encrypted = data["encriptedFilenames"]
    for i, fn in enumerate(filenames):
        if fn == str(year):
            return encrypted[i]
    return None


def download_lm_zip(year: int) -> Optional[bytes]:
    enc_key = get_enc_key(year)
    if not enc_key:
        logger.error(f"No enc key for year {year}")
        return None
    url = f"{OLMS_DOWNLOAD_URL}?report={enc_key}"
    logger.info(f"Downloading LM {year} from {url}")
    for attempt in range(1, 20):
        resp = requests.get(url, timeout=300)
        if resp.status_code == 200 and resp.content[:2] == b"PK":
            logger.info(f"Downloaded {len(resp.content):,} bytes on attempt {attempt}")
            return resp.content
        time.sleep(1)
    return None


def build_filenum_zip_map(zip_bytes: bytes) -> dict[str, str]:
    """Returns {file_number_str: zip_code_str}"""
    fnum_zip: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        data_file = next(f for f in z.namelist() if "lm_data_data" in f.lower())
        content = z.read(data_file).decode("latin-1", errors="replace")
    reader = csv.DictReader(io.StringIO(content), delimiter="|")
    for row in reader:
        fnum = str(row.get("F_NUM", "")).strip()
        zc   = str(row.get("ZIP", "")).strip()[:5].zfill(5)
        if fnum and zc and zc != "00000":
            fnum_zip[fnum] = zc
    logger.info(f"Built file_num→ZIP map: {len(fnum_zip)} entries")
    return fnum_zip


# ── Step 2: ZCTA → county_fips ───────────────────────────────────────────

def build_zip_county_map() -> dict[str, str]:
    cache = Path("../data/zip_county_map.json")
    if cache.exists():
        data = json.loads(cache.read_text())
        logger.info(f"Loaded ZIP→county map from cache: {len(data)} entries")
        return data

    logger.info("Downloading Census ZCTA-to-county crosswalk")
    resp = requests.get(ZCTA_COUNTY_URL, timeout=120)
    resp.raise_for_status()
    # Use utf-8-sig to automatically strip BOM; splitlines for clean iteration
    lines = resp.content.decode("utf-8-sig").splitlines()
    header = lines[0].split("|")

    # Find column positions by name (avoids BOM issues entirely)
    try:
        idx_oid    = header.index("OID_ZCTA5_20")
        idx_zcta   = header.index("GEOID_ZCTA5_20")
        idx_county = header.index("GEOID_COUNTY_20")
        idx_area   = header.index("AREALAND_PART")
    except ValueError as e:
        logger.error(f"ZCTA crosswalk column not found: {e}. Headers: {header[:6]}")
        return {}

    zcta_best: dict[str, tuple[str, float]] = {}  # zcta → (county_fips, land_area_part)
    for line in lines[1:]:
        if not line or line.startswith("|"):
            continue  # county-only row with no ZCTA
        fields = line.split("|")
        if len(fields) <= max(idx_oid, idx_zcta, idx_county, idx_area):
            continue
        zcta = fields[idx_zcta].strip().zfill(5)
        county_fips = fields[idx_county].strip()[:5]
        try:
            area_part = float(fields[idx_area] or 0)
        except ValueError:
            area_part = 0.0
        if zcta and county_fips:
            if zcta not in zcta_best or area_part > zcta_best[zcta][1]:
                zcta_best[zcta] = (county_fips, area_part)

    result = {z: v[0] for z, v in zcta_best.items()}
    cache.write_text(json.dumps(result, indent=2))
    logger.info(f"Built ZIP→county map: {len(result)} entries — cached")
    return result


# ── Main ──────────────────────────────────────────────────────────────────

def run(config_path: str = "../config.json", year: int = 2022):
    config = json.loads(Path(config_path).read_text())
    notion_cfg = config["notion"]
    county_ids: dict[str, str] = json.loads(Path("../data/county_ids.json").read_text())

    client = NotionClient(notion_cfg["api_key"])

    # Step 1: LM file_num → ZIP
    lm_zip = download_lm_zip(year)
    if not lm_zip:
        logger.error("Could not download LM data — aborting")
        return
    fnum_zip = build_filenum_zip_map(lm_zip)

    # Step 2: ZIP → county FIPS
    zip_county = build_zip_county_map()

    # Pre-compute: which file numbers can we resolve to a county page_id?
    # Only make Notion PATCH calls for records we know will match.
    fnum_to_page: dict[str, str] = {}
    for fnum, zc in fnum_zip.items():
        county_fips = zip_county.get(zc)
        if county_fips:
            page_id = county_ids.get(county_fips)
            if page_id:
                fnum_to_page[fnum] = page_id
    logger.info(f"{len(fnum_to_page)} file numbers resolve to a county page_id")

    # Step 3: Query UNIONS with no Primary County (Notion caps at 10k per query)
    logger.info("Querying UNIONS records with no Primary County...")
    no_county_filter = {"property": "Primary County", "relation": {"is_empty": True}}
    records = client.query_all(notion_cfg["databases"]["unions"], no_county_filter)
    logger.info(f"{len(records)} union locals have no county — checking against resolved set")

    matched = skipped = errors = 0

    for rec in records:
        props = rec.get("properties", {})
        fnum_rich = props.get("LM-2 File Number", {}).get("rich_text", [])
        fnum = fnum_rich[0]["text"]["content"].strip() if fnum_rich else ""

        page_id = fnum_to_page.get(fnum)
        if not page_id:
            skipped += 1
            continue  # no match possible — skip without any API call

        try:
            client.update_page(rec["id"], {"Primary County": relation_prop([page_id])})
            matched += 1
            if matched % 500 == 0:
                logger.info(f"Backfilled {matched} union locals so far")
            time.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed {fnum}: {e}")
            errors += 1

    logger.info(f"Backfill complete: {matched} matched, {skipped} skipped (no ZIP/county), {errors} errors")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="../config.json")
    p.add_argument("--year", type=int, default=2022)
    args = p.parse_args()
    run(args.config, args.year)
