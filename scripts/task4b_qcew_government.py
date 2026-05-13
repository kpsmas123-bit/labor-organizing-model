"""
Task 4b: Ingest QCEW government employment (own=1,2,3) into EMPLOYMENT Notion DB.

Source: BLS QCEW national annual flat file.
  agglvl=76 → county × ownership × 4-digit NAICS (core education/govt/healthcare)
  agglvl=75 → county × ownership × 3-digit NAICS (transit 485, utilities 221, sanitation 562)

Rules:
  - Do NOT modify existing CBP records (Source='Census CBP 2023')
  - Only own=1 (federal), own=2 (state), own=3 (local) — NOT own=5 (private/CBP)
  - Source field = 'QCEW_gov' on all new records
  - Record ID = {fips}-{naics}-own{own_code}  (prevents collision with CBP)
  - Suppressed cells (disclosure_code='N'): write record with null employment + Flag=True
  - Orphan fix: existing records with empty Sector relation are re-linked, not skipped

Usage:
    python task4b_qcew_government.py --config ../config.json --state 42 [--dry-run]
    python task4b_qcew_government.py --config ../config.json --all-states [--dry-run]
"""

import argparse
import csv
import io
import json
import logging
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests

sys.path.insert(0, str(Path(__file__).parent))
from notion_client import (
    NotionClient, title_prop, text_prop, number_prop,
    select_prop, checkbox_prop, relation_prop
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("../logs/task4b_qcew_government.log"),
    ],
)
logger = logging.getLogger(__name__)

QCEW_URL = "https://data.bls.gov/cew/data/files/2023/csv/2023_annual_singlefile.zip"
YEAR = 2023

# agglvl codes confirmed from flat file inspection
AGGLVL_COUNTY_4DIGIT = "76"   # county × ownership × 4-digit NAICS
AGGLVL_COUNTY_3DIGIT = "75"   # county × ownership × 3-digit NAICS

GOV_OWN_CODES = {"1", "2", "3"}   # federal, state, local

# ── NAICS → sector mapping (v6) ──────────────────────────────────────────────
# Format: naics_code → list of (allowed_own_codes_set_or_None, v6_sector_id)
# None for ownership means all government ownerships (1,2,3).
# When a NAICS maps to multiple sectors by ownership (e.g. 6222), each gets its own tuple.
NAICS_SECTOR_MAP: Dict[str, List[Tuple[Optional[Set[str]], str]]] = {
    # ── Education ────────────────────────────────────────────────────────────
    # K-12: QCEW handles government schools (own=1,2,3); CBP handles private (own=5)
    "6111": [(None, "04")],
    # Public colleges/universities (own=2,3 → 05a); private (own=5) is CBP → 05b
    "6112": [({"2", "3"}, "05a")],
    "6113": [({"2", "3"}, "05a")],
    # ── Federal hospitals and VA (federal only) ───────────────────────────────
    "6221": [({"1"}, "12")],
    # 6222 splits by ownership: federal → 12 (Federal Hospitals), state → 13 (State Public Health)
    "6222": [({"1"}, "12"), ({"2"}, "13")],
    # ── State public health (state only) ─────────────────────────────────────
    "6231": [({"2"}, "13")],   # nursing care facilities
    "6232": [({"2"}, "13")],   # residential developmental disability
    # ── Social services — 6244 (Childcare) split from 6241-6243 ─────────────
    "6241": [({"2", "3"}, "11")],
    "6242": [({"2", "3"}, "11")],
    "6243": [({"2", "3"}, "11")],
    "6244": [({"2", "3"}, "11b")],  # Childcare separated from Social Services
    # ── Public transit (state + local) — 3-digit, agglvl=75 ─────────────────
    "485":  [({"2", "3"}, "14")],
    # ── Public utilities (state + local) — 3-digit, agglvl=75 ───────────────
    "221":  [({"2", "3"}, "15")],
    # ── Public sanitation (local only) — 3-digit, agglvl=75 ─────────────────
    "562":  [({"3"}, "16")],
    # ── Public libraries (state + local) — 4-digit ───────────────────────────
    "5191": [({"2", "3"}, "17")],
    # ── Parks and recreation (state + local) — 4-digit ───────────────────────
    "7121": [({"2", "3"}, "18")],
    # ── Government administration ─────────────────────────────────────────────
    "9211": [(None, "19")],   # executive / legislative
    "9261": [(None, "19")],   # economic programs → Government Administration
    # ── Justice and police ────────────────────────────────────────────────────
    "9221": [(None, "20")],
    # ── Human services administration ────────────────────────────────────────
    "9231": [(None, "21")],   # admin of human resource programs
    "9241": [(None, "21")],   # environmental quality admin
    "9251": [(None, "21")],   # housing and urban development programs
}

TARGET_NAICS_4DIGIT = {k for k in NAICS_SECTOR_MAP if len(k) == 4}
TARGET_NAICS_3DIGIT = {k for k in NAICS_SECTOR_MAP if len(k) == 3}
TARGET_AGGLVLS = {AGGLVL_COUNTY_4DIGIT, AGGLVL_COUNTY_3DIGIT}


# ── Notion schema helper ──────────────────────────────────────────────────────

def ensure_qcew_naics_property(client: NotionClient, db_id: str) -> None:
    """Add 'QCEW NAICS Code' rich_text property to EMPLOYMENT DB if missing."""
    resp = client._request("GET", f"/databases/{db_id}")
    props = resp.get("properties", {})
    if "QCEW NAICS Code" in props:
        logger.info("'QCEW NAICS Code' property already exists in EMPLOYMENT DB")
        return
    logger.info("Adding 'QCEW NAICS Code' property to EMPLOYMENT DB...")
    client._request("PATCH", f"/databases/{db_id}", {
        "properties": {
            "QCEW NAICS Code": {"rich_text": {}}
        }
    })
    logger.info("Property added.")


# ── Record builder ────────────────────────────────────────────────────────────

def build_record(
    fips: str,
    naics: str,
    own_code: str,
    emp: Optional[int],
    is_suppressed: bool,
    county_id: str,
    sector_id: str,
    state_id: Optional[str],
) -> dict:
    record_id = f"{fips}-{naics}-own{own_code}"
    props = {
        "Record ID":          title_prop(record_id),
        "County":             relation_prop([county_id]),
        "Sector":             relation_prop([sector_id]),
        "Total Employment":   number_prop(emp),
        "Year":               number_prop(YEAR),
        "Source":             text_prop("QCEW_gov"),
        "BLS Disclosure Flag": checkbox_prop(is_suppressed),
        "Confidence":         select_prop("Low" if is_suppressed else "High"),
        "QCEW NAICS Code":    text_prop(naics),
    }
    if state_id:
        props["State"] = relation_prop([state_id])
    return props


# ── Flat file download ────────────────────────────────────────────────────────

def load_flat_file(state_filter: Optional[str] = None) -> List[dict]:
    """
    Download national QCEW annual singlefile and return relevant rows.
    state_filter: 2-digit state FIPS string (e.g. '42') to limit to one state.
    Caches in /tmp to avoid re-downloading across runs.
    """
    cache_key = state_filter or "all"
    cache_path = Path(f"/tmp/qcew_{YEAR}_{cache_key}.pkl")

    if cache_path.exists():
        import pickle
        logger.info(f"Loading cached rows from {cache_path}")
        return pickle.load(open(cache_path, "rb"))

    logger.info(f"Downloading QCEW flat file (~83MB): {QCEW_URL}")
    resp = requests.get(QCEW_URL, timeout=300)
    resp.raise_for_status()
    logger.info(f"Downloaded {len(resp.content) / 1e6:.1f} MB")

    z = zipfile.ZipFile(io.BytesIO(resp.content))
    csv_name = next(n for n in z.namelist() if n.lower().endswith(".csv"))

    rows = []
    with z.open(csv_name) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))
        for row in reader:
            area = row.get("area_fips", "")
            agglvl = row.get("agglvl_code", "")
            own = row.get("own_code", "")
            naics = row.get("industry_code", "")

            if agglvl not in TARGET_AGGLVLS:
                continue
            if own not in GOV_OWN_CODES:
                continue
            if naics not in TARGET_NAICS_4DIGIT and naics not in TARGET_NAICS_3DIGIT:
                continue
            if not area or len(area) != 5 or area.endswith("000"):
                continue  # skip state/national-level area rows

            if state_filter and not area.startswith(state_filter):
                continue

            rows.append(row)

    logger.info(f"Rows matching criteria: {len(rows):,}")

    import pickle
    pickle.dump(rows, open(cache_path, "wb"))
    logger.info(f"Cached to {cache_path}")
    return rows


# ── Main ingest ───────────────────────────────────────────────────────────────

def run(config_path: str, state_filter: Optional[str], dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())

    env_path = Path(config_path).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    notion_key = os.environ.get("NOTION_API_KEY") or config["notion"].get("api_key", "")
    db_id = config["notion"]["databases"]["employment"]

    base = Path(config_path).parent
    county_ids: dict = json.loads((base / "data/county_ids.json").read_text())
    sector_ids: dict = json.loads((base / "data/sector_ids.json").read_text())
    state_ids: dict = json.loads((base / "data/state_ids.json").read_text()) if (base / "data/state_ids.json").exists() else {}

    if not dry_run:
        client = NotionClient(notion_key)

        ensure_qcew_naics_property(client, db_id)

        # ── Build existing record index with orphan detection ─────────────────
        # Orphan: a QCEW_gov record whose Sector relation is empty because the
        # v5 sector page it pointed to was archived. We re-link these instead of
        # skipping them.
        logger.info("Fetching existing QCEW_gov record IDs (orphan detection enabled)...")
        existing_filter = {
            "property": "Source",
            "rich_text": {"equals": "QCEW_gov"}
        }
        existing_pages = client.query_all(db_id, existing_filter)

        existing_ids: Set[str] = set()
        # record_id → notion page_id for records missing their Sector relation
        sectorless_ids: Dict[str, str] = {}

        for page in existing_pages:
            title_items = page.get("properties", {}).get("Record ID", {}).get("title", [])
            if not title_items:
                continue
            rec_id = title_items[0]["text"]["content"]
            existing_ids.add(rec_id)
            sector_rel = page["properties"].get("Sector", {}).get("relation", [])
            if not sector_rel:
                sectorless_ids[rec_id] = page["id"]

        logger.info(
            f"Found {len(existing_ids)} existing QCEW_gov records "
            f"({len(sectorless_ids)} sectorless orphans to re-link)"
        )
    else:
        existing_ids = set()
        sectorless_ids = {}

    rows = load_flat_file(state_filter)
    logger.info(
        f"Processing {len(rows):,} QCEW rows "
        f"(state={'ALL' if not state_filter else state_filter})"
    )

    sup_log_path = base / "logs" / "task4b_suppressed.log"
    sup_log_path.parent.mkdir(exist_ok=True)
    sup_log = open(sup_log_path, "a") if not dry_run else None

    ok = 0
    updated = 0      # orphan records re-linked
    skipped = 0
    suppressed_written = 0
    no_county = 0
    no_sector = 0
    no_ownership = 0
    errors: list = []

    # Per-state error monitoring: halt if any state exceeds 1% error rate
    # (minimum 10 Notion attempts before triggering to avoid false positives on tiny states)
    ERROR_RATE_THRESHOLD = 0.01
    ERROR_RATE_MIN_ATTEMPTS = 10
    state_attempts: Dict[str, int] = {}
    state_errors_map: Dict[str, int] = {}
    halt_triggered = False

    for row in rows:
        if halt_triggered:
            break

        area = row["area_fips"]
        naics = row["industry_code"]
        own = row["own_code"]
        disclosure = row.get("disclosure_code", "")

        county_id = county_ids.get(area)
        if not county_id:
            no_county += 1
            continue

        state_fips = area[:2]
        state_id = state_ids.get(state_fips)

        mappings = NAICS_SECTOR_MAP.get(naics, [])
        sector_key = None
        for (allowed_owns, key) in mappings:
            if allowed_owns is None or own in allowed_owns:
                sector_key = key
                break

        if sector_key is None:
            no_ownership += 1
            continue

        sector_id = sector_ids.get(sector_key)
        if not sector_id:
            logger.warning(f"No sector_id for key={sector_key} (naics={naics})")
            no_sector += 1
            continue

        is_suppressed = (disclosure == "N")
        emp_raw = row.get("annual_avg_emplvl", "")
        if is_suppressed:
            emp = None
        else:
            try:
                emp = int(str(emp_raw).replace(",", ""))
            except Exception:
                emp = None

        if not is_suppressed and emp == 0:
            continue

        record_id = f"{area}-{naics}-own{own}"

        if record_id in existing_ids:
            if record_id in sectorless_ids and sector_id:
                # Orphan: re-link to correct v6 sector page
                if not dry_run:
                    state_attempts[state_fips] = state_attempts.get(state_fips, 0) + 1
                    try:
                        client.update_page(
                            sectorless_ids[record_id],
                            {"Sector": relation_prop([sector_id])}
                        )
                        updated += 1
                        time.sleep(0.35)
                    except Exception as e:
                        logger.error(f"Orphan re-link failed {record_id}: {e}")
                        errors.append({"record_id": record_id, "error": str(e)})
                        state_errors_map[state_fips] = state_errors_map.get(state_fips, 0) + 1
                        att = state_attempts[state_fips]
                        err = state_errors_map[state_fips]
                        if att >= ERROR_RATE_MIN_ATTEMPTS and err / att > ERROR_RATE_THRESHOLD:
                            logger.critical(
                                f"HALT: state {state_fips} error rate {err}/{att} "
                                f"({100*err/att:.1f}%) exceeds 1% threshold"
                            )
                            halt_triggered = True
                else:
                    logger.info(f"[DRY RUN] would re-link orphan {record_id} → sector {sector_key}")
                    updated += 1
            else:
                skipped += 1
            continue

        if dry_run:
            emp_display = "SUPPRESSED" if is_suppressed else str(emp)
            logger.info(f"[DRY RUN] {record_id}  emp={emp_display:>10}  sector={sector_key}")
            ok += 1
            continue

        state_attempts[state_fips] = state_attempts.get(state_fips, 0) + 1
        props = build_record(area, naics, own, emp, is_suppressed, county_id, sector_id, state_id)
        try:
            client.create_page(db_id, props)
            if is_suppressed:
                suppressed_written += 1
                if sup_log:
                    sup_log.write(f"{record_id}\t{naics}\town={own}\n")
            ok += 1
        except Exception as e:
            logger.error(f"Notion error {record_id}: {e}")
            errors.append({"record_id": record_id, "error": str(e)})
            state_errors_map[state_fips] = state_errors_map.get(state_fips, 0) + 1
            att = state_attempts[state_fips]
            err = state_errors_map[state_fips]
            if att >= ERROR_RATE_MIN_ATTEMPTS and err / att > ERROR_RATE_THRESHOLD:
                logger.critical(
                    f"HALT: state {state_fips} error rate {err}/{att} "
                    f"({100*err/att:.1f}%) exceeds 1% threshold"
                )
                halt_triggered = True

        time.sleep(0.34)

    if sup_log:
        sup_log.close()

    label = f"State {state_filter}" if state_filter else "All states"
    status = "HALTED (error rate exceeded)" if halt_triggered else "complete"
    logger.info(
        f"{label} {status}: {ok} new, {updated} orphans re-linked, {skipped} skipped, "
        f"{suppressed_written} suppressed-written, "
        f"{no_county} no county_id, {no_sector} no sector_id, "
        f"{no_ownership} ownership-filtered, {len(errors)} errors"
    )

    if dry_run:
        logger.info(f"[DRY RUN] Would write {ok} new records and re-link {updated} orphans.")

    if errors:
        err_path = base / "logs" / "task4b_errors.json"
        err_path.write_text(json.dumps(errors, indent=2))
        logger.warning(f"Errors saved to {err_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--state", help="2-digit state FIPS (e.g. 42 for PA)")
    group.add_argument("--all-states", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    state = args.state if args.state else None
    run(args.config, state, args.dry_run)
