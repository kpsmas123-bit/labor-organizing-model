"""
Second-pass union county backfill using fuzzy city-name matching.

Targets the 2,192 union locals that still have no Primary County after the
ZIP-based backfill (fix_union_county_backfill.py). Those records have missing
or unresolvable ZIP codes, so we fall back to matching on CITY + STATE.

Strategy:
  1. Query UNIONS records where Primary County is still empty
  2. For each, read the city/state stored in the LM-2 data
     (re-downloaded so we have the raw city strings)
  3. Try exact match against Census gazetteer first
  4. If that fails, try common abbreviation expansion
  5. If that fails, try Levenshtein distance ≤ 2 against gazetteer cities
     in the same state (fast because we index by state)
  6. PATCH matched records in Notion

Run after fix_union_county_backfill.py completes.

Usage:
    python fix_union_fuzzy_city.py [--config ../config.json] [--dry-run]
"""

import csv, io, json, logging, time, zipfile
from pathlib import Path
from typing import Optional

import requests, sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import NotionClient, relation_prop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / "logs" / "fix_union_fuzzy_city.log"),
    ],
)
logger = logging.getLogger(__name__)

OLMS_FILENAMES_URL = "https://olmsapps.dol.gov/olpdr/GetYearlyDownlaodFilenamesServlet"
OLMS_DOWNLOAD_URL  = "https://olmsapps.dol.gov/olpdr/GetYearlyFileServlet"

# Common abbreviations and alternate names found in LM-2 city fields
CITY_ALIASES = {
    "nyc":           ("new york", "NY"),
    "new york city": ("new york", "NY"),
    "phila":         ("philadelphia", "PA"),
    "pitts":         ("pittsburgh", "PA"),
    "chi":           ("chicago", "IL"),
    "la":            ("los angeles", "CA"),
    "sf":            ("san francisco", "CA"),
    "dc":            ("washington", "DC"),
    "wash":          ("washington", "DC"),
    "balt":          ("baltimore", "MD"),
    "bos":           ("boston", "MA"),
    "cleve":         ("cleveland", "OH"),
    "cincy":         ("cincinnati", "OH"),
    "indy":          ("indianapolis", "IN"),
    "mpls":          ("minneapolis", "MN"),
    "stl":           ("st. louis", "MO"),
    "saint louis":   ("st. louis", "MO"),
    "saint paul":    ("st. paul", "MN"),
    "n. y.":         ("new york", "NY"),
    "n.y.":          ("new york", "NY"),
}


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


def build_state_city_index(city_lookup: dict) -> dict[str, list[tuple[str, str]]]:
    """Index gazetteer cities by state for fast fuzzy matching: {state: [(city, fips)]}"""
    index: dict[str, list] = {}
    for (city, state), fips in city_lookup.items():
        index.setdefault(state, []).append((city, fips))
    return index


def fuzzy_match(city: str, state: str, index: dict, max_dist: int = 2) -> Optional[str]:
    """Return county FIPS for best fuzzy city match within max_dist, or None."""
    city_lower = city.lower().strip()
    if not city_lower or not state:
        return None

    candidates = index.get(state.upper(), [])
    best_fips = None
    best_dist = max_dist + 1

    for cand_city, fips in candidates:
        # Exact match already handled upstream; here we catch near-misses
        d = levenshtein(city_lower, cand_city)
        if d < best_dist:
            best_dist = d
            best_fips = fips

    return best_fips if best_dist <= max_dist else None


def download_lm_zip(year: int) -> Optional[bytes]:
    meta = requests.post(OLMS_FILENAMES_URL, timeout=30)
    meta.raise_for_status()
    data = meta.json()
    filenames, encrypted = data["filenames"], data["encriptedFilenames"]
    enc_key = None
    for i, fn in enumerate(filenames):
        if fn == str(year):
            enc_key = encrypted[i]
            break
    if not enc_key:
        for i, fn in enumerate(filenames):
            if fn.isdigit() and int(fn) <= year:
                enc_key = encrypted[i]
                break
    if not enc_key:
        return None
    url = f"{OLMS_DOWNLOAD_URL}?report={enc_key}"
    logger.info(f"Downloading LM {year} data")
    for attempt in range(1, 16):
        resp = requests.get(url, timeout=300)
        if resp.status_code == 200 and resp.content[:2] == b"PK":
            logger.info(f"Downloaded {len(resp.content):,} bytes on attempt {attempt}")
            return resp.content
        time.sleep(1)
    return None


def build_filenum_city_map(zip_bytes: bytes) -> dict[str, tuple[str, str]]:
    """Returns {file_number: (city, state)}"""
    result = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        data_file = next(
            (f for f in z.namelist() if "lm_data_data" in f.lower()),
            next((f for f in z.namelist() if "lm_data" in f.lower()), z.namelist()[0])
        )
        content = z.read(data_file).decode("latin-1", errors="replace")
    reader = csv.DictReader(io.StringIO(content), delimiter="|")
    for row in reader:
        fnum = str(row.get("F_NUM", "")).strip()
        city = str(row.get("CITY", "")).strip()
        state = str(row.get("STATE", "")).strip().upper()
        if fnum and city and state:
            result[fnum] = (city, state)
    logger.info(f"Built file_num→city map: {len(result)} entries")
    return result


def run(config_path: str = "../config.json", year: int = 2023, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    notion_cfg = config["notion"]
    county_ids: dict[str, str] = json.loads(Path("../data/county_ids.json").read_text())
    city_lookup_raw: dict = json.loads(Path("../data/city_county_lookup.json").read_text())

    # Reconstruct tuple-keyed dict from the stored "city|STATE" format
    city_lookup = {tuple(k.split("|")): v for k, v in city_lookup_raw.items()}
    state_index = build_state_city_index(city_lookup)
    logger.info(f"Gazetteer loaded: {len(city_lookup)} city entries across {len(state_index)} states")

    client = NotionClient(notion_cfg["api_key"])

    # Download LM data to get city/state per file number
    lm_zip = download_lm_zip(year)
    if not lm_zip:
        logger.error("Could not download LM data — aborting")
        return
    fnum_city = build_filenum_city_map(lm_zip)

    # Query only the still-unmatched unions
    logger.info("Querying UNIONS with no Primary County...")
    no_county_filter = {"property": "Primary County", "relation": {"is_empty": True}}
    records = client.query_all(notion_cfg["databases"]["unions"], no_county_filter)
    logger.info(f"{len(records)} records still unmatched — attempting fuzzy city match")

    exact = fuzzy = alias = skipped = errors = 0

    for rec in records:
        props = rec.get("properties", {})
        fnum_rich = props.get("LM-2 File Number", {}).get("rich_text", [])
        fnum = fnum_rich[0]["text"]["content"].strip() if fnum_rich else ""

        city_state = fnum_city.get(fnum)
        if not city_state:
            skipped += 1
            continue

        city_raw, state = city_state
        city_lower = city_raw.lower().strip()

        # 1. Exact match
        fips = city_lookup.get((city_lower, state))
        if fips:
            exact += 1
        else:
            # 2. Alias expansion
            alias_target = CITY_ALIASES.get(city_lower)
            if alias_target:
                expanded_city, alias_state = alias_target
                fips = city_lookup.get((expanded_city, alias_state or state))
                if fips:
                    alias += 1

        if not fips:
            # 3. Fuzzy match within state
            fips = fuzzy_match(city_lower, state, state_index, max_dist=2)
            if fips:
                fuzzy += 1

        if not fips:
            skipped += 1
            continue

        page_id = county_ids.get(fips)
        if not page_id:
            skipped += 1
            continue

        if dry_run:
            logger.info(f"DRY RUN: {fnum} '{city_raw}' {state} → {fips}")
            exact += 0  # don't double-count in dry run
            continue

        try:
            client.update_page(rec["id"], {"Primary County": relation_prop([page_id])})
            if (exact + fuzzy + alias) % 100 == 0:
                logger.info(f"Matched so far: {exact} exact, {alias} alias, {fuzzy} fuzzy")
            time.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed {fnum}: {e}")
            errors += 1

    total_matched = exact + alias + fuzzy
    logger.info(
        f"Done. {total_matched} matched ({exact} exact, {alias} alias, {fuzzy} fuzzy), "
        f"{skipped} skipped, {errors} errors"
    )


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="../config.json")
    p.add_argument("--year", type=int, default=2023)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    run(args.config, args.year, args.dry_run)
