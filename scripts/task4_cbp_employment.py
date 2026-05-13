"""
Task 4: County × Sector Employment Data — Census County Business Patterns (CBP).
v6 rewrite — NAICS 2017, v6 sector IDs, hub/rail tagging, mfg carve-outs.

Source: Census CBP API 2023 (private sector only; QCEW handles government ownerships).
Record ID: {5-digit-fips}-{naics}  (no own_code; CBP is all private-sector)

Pre-flight (runs before main loop):
  1. Archive stale CBP records (NAICS codes removed/changed in v6)
  2. Re-link CBP orphans (valid NAICS, but Sector relation empty → v5 page was archived)

Local manifest (data/cbp_record_ids.txt):
  One record ID per line. Used for O(1) dedup without Notion query_all cap (10K limit).
  Populated by --backfill-manifest before first --all-states run.

Usage:
    python task4_cbp_employment.py --config ../config.json --state 21 [--dry-run]
    python task4_cbp_employment.py --config ../config.json --all-states
    python task4_cbp_employment.py --config ../config.json --state 21 --backfill-manifest

    --phase 1: top ~100 counties by population (~60% of US employment)
    --phase 2: next ~400 counties (~90%)
    --phase 3: remaining counties
"""

import json
import logging
import argparse
import time
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests
import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import (
    NotionClient, title_prop, text_prop, number_prop,
    select_prop, checkbox_prop, relation_prop
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("../logs/task4_cbp_employment.log"),
    ],
)
logger = logging.getLogger(__name__)

CBP_API = "https://api.census.gov/data/2023/cbp"
CBP_YEAR = "2023"

# Local manifest file for dedup (avoids Notion query_all 10K cap)
MANIFEST_PATH_NAME = "data/cbp_record_ids.txt"

# ── Sector routing ─────────────────────────────────────────────────────────────
# Direct routes: cbp_naics → v6 sector_id
# Multiple NAICS codes can map to the same sector (e.g. 6211+6212 → "03c").
# task9 uses += accumulation so multiple records per sector sum correctly.
DIRECT_ROUTES: Dict[str, str] = {
    # Healthcare (private, own=5)
    "622":   "01",    # Hospitals
    "623":   "02",    # Nursing Homes
    "6216":  "03a",   # Home Health
    "6214":  "03b",   # Outpatient Care
    "6211":  "03c",   # Physician Offices
    "6212":  "03c",   # Dentist Offices
    "6215":  "03d",   # Medical Labs
    # Education (private; public K-12 and colleges handled by task4b/QCEW)
    "6111":  "04",    # K-12 private (CBP = private schools, tutoring chains)
    "6112":  "05b",   # Private Universities
    "6113":  "05b",   # Private Community Colleges
    # Logistics
    "4883":  "06",    # Ports (Support Activities for Water Transportation)
    "4841":  "07a",   # Trucking General (General Freight Trucking)
    "4931":  "08",    # Warehousing
    "481":   "10",    # Air Transportation
    # Social Services (6241-6243 direct; 6244/childcare handled separately below)
    "6241":  "11",    # Individual & Family Services
    "6242":  "11",    # Community Food, Housing & Emergency
    "6243":  "11",    # Vocational Rehabilitation
    # Other services
    "23":    "24",    # Construction (all: 236+237+238 rolled into 2-digit in v6)
    "722":   "26",    # Food Service & Drinking Places
    "721":   "27",    # Hotels & Other Accommodations
    "44-45": "25",    # Retail Trade
    # Energy
    "211":   "28",    # Oil & Gas Extraction
    "212":   "28",    # Mining (except Oil & Gas)
    "213":   "28",    # Support Activities for Mining
    # Tech/Info — query sub-codes individually to avoid double-count with 517=Telecom
    # Do NOT query "51" aggregate (would double-count 517)
    # 513/514 discontinued in NAICS 2002 — not present in CBP 2023
    "511":   "29",    # Publishing (except Internet)
    "512":   "29",    # Motion Picture & Sound Recording
    "515":   "29",    # Broadcasting (except Internet, Radio/TV)
    "518":   "29",    # Data Processing, Hosting & Related
    "519":   "29",    # Other Information Services
    # Telecom (queried separately from Tech to allow different sector routing)
    "517":   "30",    # Telecommunications
    # Finance & Agriculture
    "52":    "31",    # Finance & Banking (Insurance/Real Estate excluded)
    "11":    "32",    # Agriculture (Crop/Livestock production & support)
}

# Manufacturing carve-out NAICS (not in DIRECT_ROUTES; resolved by resolve_mfg_carveouts())
MFG_TOTAL_NAICS  = "31-33"   # All manufacturing — used as parent for carve-out math
MFG_AUTO_NAICS   = "3361"    # Motor Vehicle Mfg → sector 22
MFG_AERO_NAICS   = "3364"    # Aerospace Product & Parts → sector 23b
# Residual (31-33 minus auto minus aero) → sector 23 (Mfg General)

# Minimum parent employment before applying absence-based proportion estimates.
# Below this threshold, a 4-digit carve-out code that is absent from CBP response
# is treated as genuinely zero (no large employer present). Above it, absence is
# more likely CBP suppression (county has a large but identifiable auto/aero plant).
# 500 is the breakpoint: 9.5% × 500 = ~48 auto workers — detectable and plausible.
# 9.5% × 200 = 19 auto workers — below meaningful organising resolution; skip.
MFG_CARVEOUT_ABSENCE_THRESHOLD = 500

# Childcare: 6244 handled separately from DIRECT_ROUTES
CHILDCARE_NAICS        = "6244"
CHILDCARE_PARENT_NAICS = "624"   # parent for estimation if 6244 is suppressed
CHILDCARE_PROPORTION   = 0.18    # national average 6244 share of 624 total

# Courier hub tagging: FIPS → v6 sector_id
# Default (non-hub counties): "07d"
COURIER_NAICS = "4922"
COURIER_HUB_MAP: Dict[str, str] = {
    "21111": "07b",   # Jefferson KY — UPS Worldport (Louisville)
    "47157": "07c",   # Shelby TN   — FedEx Memphis SuperHub
    "04013": "07c",   # Maricopa AZ — FedEx Phoenix Sky Harbor hub
}

# Rail passenger hub counties → sector "09b"; all other NAICS 482 counties → "09a"
RAIL_NAICS = "482"
RAIL_PASSENGER_HUBS: Set[str] = {
    # NYC metro (Penn/Grand Central/PATH hubs)
    "36061", "36047", "36081", "36005",   # Manhattan, Brooklyn, Queens, Bronx
    "34017", "34013",                      # Hudson NJ (Hoboken), Essex NJ (Newark)
    # Chicago (Union Station)
    "17031", "17043",                      # Cook IL, DuPage IL
    # DC metro (Union Station, Virginia Rail)
    "11001", "51013", "51510", "24031", "24033",
    # Bay Area (BART, Caltrain, Capitol Corridor)
    "06075", "06001", "06013", "06081", "06085",
    # Los Angeles (Metrolink, Amtrak Pacific Surfliner)
    "06037", "06059",
    # Philadelphia metro (SEPTA Regional Rail)
    "42101", "42045", "42091", "42017",
    # Boston metro (MBTA Commuter Rail)
    "25025", "25017", "25021",
    # Seattle (Amtrak Cascades)
    "53033",
    # Portland (Amtrak Cascades)
    "41051",
    # Baltimore (MARC, Amtrak)
    "24510",
    # Denver (RTD commuter rail)
    "08031",
    # Connecticut Metro-North
    "09009", "09003",                      # New Haven CT, Hartford CT
    # Other major Amtrak hubs
    "06073",   # San Diego (Pacific Surfliner/Coaster)
    "27053",   # Hennepin MN (Northstar)
    "55079",   # Milwaukee WI (Amtrak Hiawatha)
    "37119",   # Mecklenburg NC
    "13121",   # Fulton GA (Amtrak Crescent)
    "22071",   # Orleans Parish LA (Amtrak Sunset/Crescent)
}

# FIPS → 2-letter abbreviation (for state_ids.json lookup, which is keyed by abbrev)
STATE_FIPS_TO_ABBREV: Dict[str, str] = {
    "01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE",
    "11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA",
    "20":"KS","21":"KY","22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN",
    "28":"MS","29":"MO","30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM",
    "36":"NY","37":"NC","38":"ND","39":"OH","40":"OK","41":"OR","42":"PA","44":"RI",
    "45":"SC","46":"SD","47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA",
    "54":"WV","55":"WI","56":"WY","72":"PR",
}

# NAICS codes from v5 that no longer exist in v6 (stale) — archive before re-run
# "31-33" is stale because v5 stored full mfg total; v6 stores residual (excl. auto/aero)
STALE_CBP_NAICS: Set[str] = {
    "621",              # replaced by 4-digit sub-codes (6211, 6212, 6214, 6215)
    "484",              # replaced by 4841 (General Freight Trucking only)
    "492",              # replaced by 4922 (Couriers & Express Delivery)
    "488",              # replaced by 4883 (Water Transportation Support only)
    "493",              # replaced by 4931 (Warehousing 4-digit)
    "236", "237", "238",  # replaced by 23 (Construction total 2-digit)
    "221",              # utilities moved to QCEW only (public sector, own=2,3)
    "31-33",            # v5: total mfg; v6: residual mfg general (different value)
}

# NAICS codes whose v5 CBP records can be re-linked to v6 sector pages
# (record IDs unchanged; only the Sector relation pointer needs updating)
RELINK_CBP_NAICS_MAP: Dict[str, str] = {
    naics: sid for naics, sid in DIRECT_ROUTES.items()
}
# Also include carve-out and special-case NAICS
RELINK_CBP_NAICS_MAP.update({
    COURIER_NAICS: "07d",    # default; hub-tagged counties handled during main loop re-link
    RAIL_NAICS: "09a",       # default; passenger-hub counties handled during main loop re-link
    MFG_TOTAL_NAICS: "23",   # now stores residual value — still maps to Mfg General
    MFG_AUTO_NAICS: "22",
    MFG_AERO_NAICS: "23b",
    CHILDCARE_NAICS: "11b",
    # 6-digit codes that v5 occasionally wrote (more specific than our 4-digit targets)
    "621910": "03a",   # Home Health Care Services (6-digit) → Home Health
    "621610": "03a",   # same sub-sector variant
    "622110": "01",    # General Medical & Surgical Hospitals → Hospitals
    "622210": "01",    # Psychiatric & Substance Abuse Hospitals → Hospitals
    "622310": "01",    # Specialty Hospitals → Hospitals
    "623110": "02",    # Nursing Care Facilities → Nursing Homes
    "623210": "02",    # Residential Intellectual/Dev Disability → Nursing Homes
    "623220": "02",    # Residential Mental Health → Nursing Homes
    "623310": "02",    # Continuing Care Retirement → Nursing Homes
    "623990": "02",    # Other Residential Care → Nursing Homes
})


# ── Local manifest helpers ─────────────────────────────────────────────────────

def load_manifest(base: Path) -> Set[str]:
    """Load existing record IDs from local manifest file. Returns empty set if missing."""
    path = base / MANIFEST_PATH_NAME
    if not path.exists():
        return set()
    lines = path.read_text().splitlines()
    return {line.strip() for line in lines if line.strip()}


def append_to_manifest(base: Path, record_ids: List[str]) -> None:
    """Append new record IDs to local manifest file (one per line, append-only)."""
    if not record_ids:
        return
    path = base / MANIFEST_PATH_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for rid in record_ids:
            f.write(rid + "\n")


# ── Census API helpers ─────────────────────────────────────────────────────────

def load_census_key(config_path: str) -> str:
    """Load Census API key from .env or config.json."""
    env_path = Path(config_path).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("CENSUS_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    key = os.environ.get("CENSUS_API_KEY", "")
    if key:
        return key
    raise ValueError("CENSUS_API_KEY not found in .env or environment. Add it before running task4.")


def fetch_county_employment(
    state_fips: str, county_fips: str, census_key: str
) -> Tuple[Dict[str, Optional[int]], Set[str]]:
    """
    Fetch ALL NAICS employment for one county in a single CBP API call.
    Returns (emp_by_naics, suppressed_set).
      emp_by_naics[naics] = int(employment) or None (if suppressed)
      suppressed_set = set of NAICS codes with suppressed ("N") employment
    """
    params = {
        "get": "EMP,NAICS2017",
        "for": f"county:{county_fips}",
        "in": f"state:{state_fips}",
        "key": census_key,
    }
    resp = requests.get(CBP_API, params=params, timeout=30)
    resp.raise_for_status()
    if resp.text.strip().startswith("<"):
        raise ValueError(f"Census API returned HTML (auth error?): {resp.text[:300]}")
    data = resp.json()
    header = data[0]
    # CBP API quirk: NAICS2017 appears twice (code + label); first occurrence = code
    naics_idx = header.index("NAICS2017")
    emp_idx   = header.index("EMP")

    emp: Dict[str, Optional[int]] = {}
    suppressed: Set[str] = set()
    for row in data[1:]:
        naics   = row[naics_idx]
        emp_raw = row[emp_idx]
        if emp_raw == "N":
            emp[naics] = None
            suppressed.add(naics)
        elif emp_raw not in ("", "0", None):
            try:
                emp[naics] = int(str(emp_raw).replace(",", ""))
            except (ValueError, TypeError):
                pass
    return emp, suppressed


# ── Carve-out resolvers ────────────────────────────────────────────────────────

def resolve_mfg_carveouts(
    emp: Dict[str, Optional[int]], suppressed: Set[str]
) -> List[Tuple[str, str, int, str]]:
    """
    Returns list of (record_naics_key, sector_id, employment, confidence) for mfg sectors.
    record_naics_key is used as the NAICS part of Record ID.

    Sectors produced:
      "3361" → "22" (Mfg Auto)    — direct or estimated at 9.5% of 31-33
      "3364" → "23b" (Mfg Aero)   — direct or estimated at 3.5% of 31-33
      "31-33" → "23" (Mfg General) — residual (total minus auto minus aero)

    confidence = "High" for direct CBP data, "Low" for proportion estimates.

    Three cases per carve-out NAICS:
      a) Direct CBP value → use it, confidence=High
      b) CBP returns "N" (suppressed) → estimate at proportion of parent, confidence=Low
      c) Absent from CBP response AND parent ≥ 500 → estimate (likely suppressed
         large employer), confidence=Low
      d) Absent AND parent < 500 → skip (genuinely no auto/aero in this county)

    A4 fallback: if parent 31-33 is suppressed or absent, return [] for all three.
    """
    mfg_total = emp.get(MFG_TOTAL_NAICS)
    if MFG_TOTAL_NAICS in suppressed or not mfg_total:
        return []  # Parent suppressed/absent → skip all three

    def carveout(naics: str, proportion: float) -> Tuple[int, str]:
        """Returns (employment, confidence)."""
        val = emp.get(naics)
        if val is not None:
            return val, "High"   # Case a: direct CBP data
        if naics in suppressed:
            return round(proportion * mfg_total), "Low"  # Case b: explicit suppression
        # Case c/d: absent from response — check parent threshold
        if mfg_total >= MFG_CARVEOUT_ABSENCE_THRESHOLD:
            # Large parent → absence is likely CBP suppression of identifiable employer
            return round(proportion * mfg_total), "Low"
        return 0, "High"  # Case d: small parent → genuinely no auto/aero here

    auto_emp, auto_conf = carveout(MFG_AUTO_NAICS, 0.095)
    aero_emp, aero_conf = carveout(MFG_AERO_NAICS, 0.035)
    residual = max(0, mfg_total - auto_emp - aero_emp)

    results: List[Tuple[str, str, int, str]] = []
    if auto_emp  > 0: results.append((MFG_AUTO_NAICS,  "22",  auto_emp, auto_conf))
    if aero_emp  > 0: results.append((MFG_AERO_NAICS,  "23b", aero_emp, aero_conf))
    if residual  > 0: results.append((MFG_TOTAL_NAICS, "23",  residual, "High"))
    return results


def resolve_childcare(
    emp: Dict[str, Optional[int]], suppressed: Set[str]
) -> Optional[int]:
    """
    Returns childcare employment for sector 11b (6244), or None to skip.
    Falls back to 18% of NAICS 624 total if 6244 is suppressed but 624 is available.
    """
    val = emp.get(CHILDCARE_NAICS)
    if val is not None:
        return val                                   # Direct 6244 data

    if CHILDCARE_NAICS in suppressed:
        parent = emp.get(CHILDCARE_PARENT_NAICS)
        if parent and CHILDCARE_PARENT_NAICS not in suppressed:
            return round(CHILDCARE_PROPORTION * parent)  # Estimated

    return None  # Not present or double-suppressed


# ── Notion schema helper ───────────────────────────────────────────────────────

def ensure_cbp_naics_property(client: NotionClient, db_id: str) -> None:
    """Add 'CBP NAICS Code' rich_text property to EMPLOYMENT DB if missing."""
    resp = client._request("GET", f"/databases/{db_id}")
    if "CBP NAICS Code" in resp.get("properties", {}):
        logger.info("'CBP NAICS Code' property already exists")
        return
    logger.info("Adding 'CBP NAICS Code' property to EMPLOYMENT DB...")
    client._request("PATCH", f"/databases/{db_id}", {
        "properties": {"CBP NAICS Code": {"rich_text": {}}}
    })
    logger.info("Property added.")


# ── Record builder ─────────────────────────────────────────────────────────────

def build_record(
    fips: str, record_id: str, naics: str, emp_val: int,
    county_id: str, sector_id: str,
    state_id: Optional[str] = None,
    confidence: str = "High",
) -> dict:
    props = {
        "Record ID":          title_prop(record_id),
        "County":             relation_prop([county_id]),
        "Sector":             relation_prop([sector_id]),
        "Total Employment":   number_prop(emp_val),
        "Year":               number_prop(int(CBP_YEAR)),
        "Source":             text_prop(f"Census CBP {CBP_YEAR}"),
        "BLS Disclosure Flag": checkbox_prop(False),
        "Confidence":         select_prop(confidence),
        "CBP NAICS Code":     text_prop(naics),
    }
    if state_id:
        props["State"] = relation_prop([state_id])
    return props


# ── NAICS code extraction from Record ID ──────────────────────────────────────

def naics_from_record_id(rec_id: str) -> str:
    """Extract NAICS portion from '{5-digit-fips}-{naics}'. FIPS is always 5 chars."""
    return rec_id[6:] if len(rec_id) > 6 else ""


# ── Manifest backfill ──────────────────────────────────────────────────────────

def backfill_manifest(
    client: NotionClient, db_id: str, base: Path,
    fips_list: List[str], state_ids: Dict[str, str],
    county_ids_lookup: Dict[str, str],
) -> None:
    """
    Populate local manifest from Notion for the given counties.
    Queries state-by-state to avoid the 10K query_all cap.
    Safe to run multiple times — skips IDs already in manifest.
    """
    fips_set = set(fips_list)
    states = sorted({f[:2] for f in fips_list})
    existing_manifest = load_manifest(base)
    logger.info(
        f"Backfilling manifest for {len(fips_list)} counties in {len(states)} states "
        f"({len(existing_manifest)} already in manifest)..."
    )
    total_added = 0
    for state_fips in states:
        # Query county-by-county — each county has ≤20 CBP records (well under 10K cap).
        # This is reliable even when State relation was not set on existing records.
        state_fips_counties = [f for f in fips_list if f[:2] == state_fips]
        pages = []
        for cfips in state_fips_counties:
            county_page_id = county_ids_lookup.get(cfips)
            if not county_page_id:
                continue
            county_filter = {
                "and": [
                    {"property": "Source",  "rich_text": {"equals": f"Census CBP {CBP_YEAR}"}},
                    {"property": "County",  "relation": {"contains": county_page_id}},
                ]
            }
            county_pages = client.query_all(db_id, county_filter)
            pages.extend(county_pages)
            time.sleep(0.1)
        new_ids: List[str] = []
        for page in pages:
            title_items = page["properties"].get("Record ID", {}).get("title", [])
            if not title_items:
                continue
            rec_id = title_items[0]["text"]["content"]
            if rec_id[:5] in fips_set and rec_id not in existing_manifest:
                new_ids.append(rec_id)
                existing_manifest.add(rec_id)
        if new_ids:
            append_to_manifest(base, new_ids)
            total_added += len(new_ids)
            logger.info(f"  State {state_fips}: {len(new_ids)} records added to manifest")
        else:
            logger.info(f"  State {state_fips}: 0 new records (all already in manifest or none found)")

    logger.info(f"Backfill complete: {total_added} record IDs added to manifest")


# ── Main run ───────────────────────────────────────────────────────────────────

def run(
    config_path: str, fips_list: List[str],
    dry_run: bool = False, do_backfill: bool = False
):
    config = json.loads(Path(config_path).read_text())
    base   = Path(config_path).parent
    db_id  = config["notion"]["databases"]["employment"]

    county_ids: dict = json.loads((base / "data/county_ids.json").read_text())
    sector_ids: dict = json.loads((base / "data/sector_ids.json").read_text())
    state_ids: dict  = json.loads((base / "data/state_ids.json").read_text()) \
                       if (base / "data/state_ids.json").exists() else {}

    census_key = load_census_key(config_path)
    notion_key = config["notion"]["api_key"]

    if not dry_run:
        client = NotionClient(notion_key)
        ensure_cbp_naics_property(client, db_id)

        # ── Backfill-manifest mode ────────────────────────────────────────────
        if do_backfill:
            backfill_manifest(client, db_id, base, fips_list, state_ids, county_ids)
            return

        # ── Load manifest (local dedup — replaces Notion query_all for existing IDs) ─
        existing_ids: Set[str] = load_manifest(base)
        logger.info(f"Manifest loaded: {len(existing_ids)} existing record IDs")

        # ── Pre-flight: stale/orphan detection (Notion, scoped to fips_set) ───
        # Querying only records in scope keeps each query << 10K even for large runs.
        # For single-state: ~1,500 records. For --all-states in phases: still bounded.
        logger.info("Fetching existing CBP records (archive/re-link pre-flight)...")
        existing_filter = {
            "property": "Source",
            "rich_text": {"equals": f"Census CBP {CBP_YEAR}"}
        }
        existing_pages = client.query_all(db_id, existing_filter)

        stale_pages:    Dict[str, str] = {}   # record_id → page_id (to archive)
        sectorless_ids: Dict[str, str] = {}   # record_id → page_id (to re-link)

        fips_set = set(fips_list)  # scope pre-flight to counties in this run
        for page in existing_pages:
            title_items = page["properties"].get("Record ID", {}).get("title", [])
            if not title_items:
                continue
            rec_id     = title_items[0]["text"]["content"]
            fips_part  = rec_id[:5]
            naics_part = naics_from_record_id(rec_id)

            if fips_part not in fips_set:
                continue  # Out-of-scope county — manifest handles dedup for those

            if naics_part in STALE_CBP_NAICS:
                stale_pages[rec_id] = page["id"]
            else:
                sector_rel = page["properties"].get("Sector", {}).get("relation", [])
                if not sector_rel:
                    sectorless_ids[rec_id] = page["id"]
                else:
                    existing_ids.add(rec_id)  # Active in-scope record → dedup guard

        logger.info(
            f"Existing CBP records: {len(existing_ids)} total (manifest), "
            f"{len(stale_pages)} stale to archive, "
            f"{len(sectorless_ids)} orphans to re-link"
        )

        # ── Archive stale records ─────────────────────────────────────────────
        archived = 0
        arch_errors = 0
        for rec_id, page_id in stale_pages.items():
            naics_part = naics_from_record_id(rec_id)
            try:
                client.archive_page(page_id)
                archived += 1
                existing_ids.discard(rec_id)  # Remove from in-memory dedup set
                logger.debug(f"Archived stale: {rec_id} (NAICS {naics_part})")
                time.sleep(0.35)
            except Exception as e:
                logger.error(f"Archive failed {rec_id}: {e}")
                arch_errors += 1
        if stale_pages:
            logger.info(f"Pre-flight archive: {archived} stale records archived, {arch_errors} errors")

        # ── Re-link orphaned records ──────────────────────────────────────────
        relinked = 0
        relink_errors = 0
        for rec_id, page_id in sectorless_ids.items():
            naics_part = naics_from_record_id(rec_id)
            sector_key = RELINK_CBP_NAICS_MAP.get(naics_part)
            if not sector_key:
                logger.warning(f"Re-link: no sector map for NAICS {naics_part} (record {rec_id})")
                continue
            sector_id = sector_ids.get(sector_key)
            if not sector_id:
                logger.warning(f"Re-link: no sector_id for key={sector_key} (record {rec_id})")
                continue
            try:
                client.update_page(page_id, {"Sector": relation_prop([sector_id])})
                relinked += 1
                existing_ids.add(rec_id)   # Re-linked record exists; skip in main loop
                time.sleep(0.35)
            except Exception as e:
                logger.error(f"Re-link failed {rec_id}: {e}")
                relink_errors += 1
        if sectorless_ids:
            logger.info(f"Pre-flight re-link: {relinked} orphans re-linked, {relink_errors} errors")
    else:
        existing_ids = set()

    # ── Main ingest loop ──────────────────────────────────────────────────────
    ok               = 0   # new records created
    skipped          = 0   # already existed, no action needed
    no_county        = 0
    no_sector        = 0
    no_data          = 0   # NAICS code absent in this county
    errors: List[dict] = []

    # Per-state error monitoring (halt if >1% error rate with ≥10 attempts)
    ERROR_RATE_THRESHOLD   = 0.01
    ERROR_RATE_MIN_ATTEMPTS = 10
    state_attempts:   Dict[str, int] = {}
    state_errors_map: Dict[str, int] = {}
    halt_triggered = False

    logger.info(f"Processing {len(fips_list)} counties")

    for i, fips in enumerate(fips_list, 1):
        if halt_triggered:
            break

        county_id = county_ids.get(fips)
        if not county_id:
            no_county += 1
            continue

        state_fips   = fips[:2]
        county_fips3 = fips[2:]
        state_abbrev = STATE_FIPS_TO_ABBREV.get(state_fips)
        state_id     = state_ids.get(state_abbrev) if state_abbrev else None

        if dry_run:
            logger.info(f"[DRY RUN] {fips} state={state_fips}")
            ok += 1
            continue

        # Fetch all NAICS employment for this county (one API call)
        try:
            emp, suppressed = fetch_county_employment(state_fips, county_fips3, census_key)
        except Exception as e:
            logger.error(f"CBP fetch failed for {fips}: {e}")
            errors.append({"fips": fips, "error": str(e)})
            state_errors_map[state_fips] = state_errors_map.get(state_fips, 0) + 1
            state_attempts[state_fips]   = state_attempts.get(state_fips, 0) + 1
            att = state_attempts[state_fips]; err = state_errors_map[state_fips]
            if att >= ERROR_RATE_MIN_ATTEMPTS and err / att > ERROR_RATE_THRESHOLD:
                logger.critical(f"HALT: state {state_fips} error rate {err}/{att} ({100*err/att:.1f}%) > 1%")
                halt_triggered = True
            time.sleep(2)
            continue

        # Build list of (naics_key, sector_key, emp_val, confidence) for this county
        records: List[Tuple[str, str, int, str]] = []

        # 1. Direct routes
        for naics, sector_key in DIRECT_ROUTES.items():
            val = emp.get(naics)
            if val is None and naics not in suppressed:
                no_data += 1
                continue
            if val is not None and val <= 0:
                no_data += 1
                continue
            records.append((naics, sector_key, val or 0, "High"))

        # 2. Courier hub tagging (NAICS 4922)
        courier_emp = emp.get(COURIER_NAICS)
        if courier_emp and courier_emp > 0:
            sector_key = COURIER_HUB_MAP.get(fips, "07d")
            records.append((COURIER_NAICS, sector_key, courier_emp, "High"))

        # 3. Rail tagging (NAICS 482)
        rail_emp = emp.get(RAIL_NAICS)
        if rail_emp and rail_emp > 0:
            sector_key = "09b" if fips in RAIL_PASSENGER_HUBS else "09a"
            records.append((RAIL_NAICS, sector_key, rail_emp, "High"))

        # 4. Mfg carve-outs (3361, 3364, 31-33 residual) — may include Low confidence
        for naics_key, sector_key, emp_val, conf in resolve_mfg_carveouts(emp, suppressed):
            records.append((naics_key, sector_key, emp_val, conf))

        # 5. Childcare (6244 with 624-based fallback)
        childcare_emp = resolve_childcare(emp, suppressed)
        if childcare_emp and childcare_emp > 0:
            records.append((CHILDCARE_NAICS, "11b", childcare_emp, "High"))

        # Write records to Notion
        new_ids_this_county: List[str] = []
        for naics_key, sector_key, emp_val, confidence in records:
            record_id = f"{fips}-{naics_key}"

            if record_id in existing_ids:
                skipped += 1
                continue

            sector_id = sector_ids.get(sector_key)
            if not sector_id:
                logger.warning(f"No sector_id for key={sector_key} (fips={fips} naics={naics_key})")
                no_sector += 1
                continue

            props = build_record(
                fips, record_id, naics_key, emp_val,
                county_id, sector_id, state_id, confidence
            )
            state_attempts[state_fips] = state_attempts.get(state_fips, 0) + 1
            try:
                client.create_page(db_id, props)
                existing_ids.add(record_id)
                new_ids_this_county.append(record_id)
                ok += 1
            except Exception as e:
                logger.error(f"Notion error {record_id}: {e}")
                errors.append({"record_id": record_id, "error": str(e)})
                state_errors_map[state_fips] = state_errors_map.get(state_fips, 0) + 1
                att = state_attempts[state_fips]; err_cnt = state_errors_map[state_fips]
                if att >= ERROR_RATE_MIN_ATTEMPTS and err_cnt / att > ERROR_RATE_THRESHOLD:
                    logger.critical(
                        f"HALT: state {state_fips} error rate {err_cnt}/{att} "
                        f"({100*err_cnt/att:.1f}%) > 1% threshold"
                    )
                    halt_triggered = True

            time.sleep(0.34)

        # Flush new IDs for this county to manifest (durable even if run is interrupted)
        if new_ids_this_county:
            append_to_manifest(base, new_ids_this_county)

        if i % 25 == 0:
            logger.info(f"Progress: {i}/{len(fips_list)} counties | new={ok} skip={skipped} err={len(errors)}")

        time.sleep(0.3)  # CBP rate limit (API allows ~3–5 req/s; be polite)

    status = "HALTED (error rate exceeded)" if halt_triggered else "complete"
    logger.info(
        f"Run {status}: {ok} new records, {skipped} skipped (already exist), "
        f"{no_data} no data, {no_county} no county_id, {no_sector} no sector_id, "
        f"{len(errors)} errors"
    )
    if errors:
        err_path = Path(config_path).parent / "logs/task4_cbp_errors.json"
        err_path.write_text(json.dumps(errors, indent=2))
        logger.warning(f"Errors saved to {err_path}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Task 4 v6: CBP employment ingestion")
    parser.add_argument("--config", default="../config.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--phase", type=int, choices=[1, 2, 3],
                       help="Phase 1: top 100 counties; 2: next 400; 3: remaining")
    group.add_argument("--state", metavar="FIPS",
                       help="2-digit state FIPS for single-state test run (e.g. 21 for KY)")
    group.add_argument("--all-states", action="store_true",
                       help="Run all counties in all states")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backfill-manifest", action="store_true",
                        help="Populate manifest from Notion for existing records (run once before --all-states)")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text())
    base   = Path(args.config).parent
    county_ids: dict = json.loads((base / "data/county_ids.json").read_text())
    all_fips = sorted(county_ids.keys())

    if args.state:
        fips_list = [f for f in all_fips if f.startswith(args.state.zfill(2))]
        logger.info(f"State {args.state}: {len(fips_list)} counties")
    elif args.all_states:
        fips_list = all_fips
        logger.info(f"All states: {len(fips_list)} counties")
    else:
        priority = config["priority_counties"]["phase_1_top_100"]
        if args.phase == 1:
            fips_list = [f for f in priority if f in county_ids][:100]
        elif args.phase == 2:
            done = set(priority[:100])
            fips_list = [f for f in all_fips if f not in done][:400]
        else:
            done = set(priority[:100]) | set(
                f for f in all_fips if f not in set(priority[:100])
            )
            fips_list = [f for f in all_fips if f not in done]
        logger.info(f"Phase {args.phase}: {len(fips_list)} counties")

    run(args.config, fips_list, args.dry_run, do_backfill=args.backfill_manifest)


if __name__ == "__main__":
    main()
