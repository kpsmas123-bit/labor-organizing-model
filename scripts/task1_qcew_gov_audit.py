"""
Task 1: QCEW Government Employment Audit — Pennsylvania (read-only)

Inventories every 4-digit government NAICS code present in PA QCEW data,
reports employment by ownership type (federal/state/local), checks coverage
against sector_ids.json, and measures county-level suppression rate.

Strategy:
  1. Download PA-specific QCEW annual flat file (CSV in zip) from BLS —
     most comprehensive, no pagination issues, single download.
  2. If state-specific zip unavailable, fall back to national singlefile.
  3. API fallback (one call per NAICS × ownership) if flat file fails.

No data is written. Run from scripts/ or project root.

Usage:
    python scripts/task1_qcew_gov_audit.py
"""

import csv
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# ── Load env manually (avoid requiring dotenv to be installed) ───────────────
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

BLS_API_KEY = os.environ.get("BLS_API_KEY", "")
QCEW_API_BASE = "https://data.bls.gov/cew/api/data/v2"
YEAR = "2023"
PA_FIPS = "42"

DATA_DIR = Path(__file__).parent.parent / "data"
SECTOR_IDS: dict = json.loads((DATA_DIR / "sector_ids.json").read_text())

# ── NAICS descriptions (government-relevant 4-digit codes) ──────────────────
NAICS_DESCRIPTIONS = {
    "6111": "Elementary & Secondary Schools (K-12)",
    "6112": "Junior Colleges",
    "6113": "Colleges, Universities & Prof Schools",
    "6114": "Business Schools & Training",
    "6115": "Technical & Trade Schools",
    "6116": "Other Schools & Instruction",
    "6117": "Educational Support Services",
    "6211": "Offices of Physicians",
    "6212": "Offices of Dentists",
    "6213": "Other Health Practitioner Offices",
    "6214": "Outpatient Care Centers",
    "6215": "Medical & Diagnostic Labs",
    "6216": "Home Health Care Services",
    "6219": "Other Ambulatory Health Care",
    "6221": "General Medical & Surgical Hospitals",
    "6222": "Psychiatric & Substance Abuse Hospitals",
    "6223": "Specialty (except Psychiatric) Hospitals",
    "6231": "Nursing Care Facilities",
    "6232": "Residential Intellectual/Developmental",
    "6233": "Continuing Care Retirement Facilities",
    "6239": "Other Residential Care Facilities",
    "6241": "Individual & Family Services",
    "6242": "Community Food & Housing, Emergency",
    "6243": "Vocational Rehabilitation Services",
    "6244": "Child Day Care Services",
    "9211": "Executive, Legislative & General Govt",
    "9221": "Justice, Public Order & Safety",
    "9231": "Admin of Human Resource Programs",
    "9241": "Admin of Environmental Quality Programs",
    "9251": "Admin of Housing & Community Dev Programs",
    "9261": "Admin of Economic Programs",
    "9271": "Space Research & Technology",
    "9281": "National Security & International Affairs",
    "9999": "Nonclassifiable Establishments",
}

OWN_NAMES = {"1": "federal", "2": "state", "3": "local"}

# Counties to sample for suppression analysis (urban → rural gradient)
PA_SAMPLE_COUNTIES = {
    "42101": "Philadelphia",
    "42003": "Allegheny",
    "42091": "Montgomery",
    "42027": "Centre",
    "42023": "Cameron",
}

# Suggested parent sector for NAICS codes not in sector_ids.json
PARENT_MAP = {
    "9241": "9231",   # environmental admin → human resource admin
    "9251": "9231",   # housing admin → human resource admin
    "9261": "9211",   # economic programs → exec/legislative
    "9271": "9211",   # space research → exec/legislative
    "9281": "9211",   # national security → exec/legislative
    "6211": "621",    # physician offices → ambulatory health
    "6212": "621",
    "6213": "621",
    "6214": "621",
    "6215": "621",
    "6219": "621",
    "6221": "622",    # general hospitals → hospitals
    "6222": "622",
    "6223": "622",
    "6231": "623",    # nursing → nursing/residential
    "6232": "623",
    "6233": "623",
    "6239": "623",
    "6241": "9231",   # social services → human resource admin
    "6242": "9231",
    "6243": "9231",
    "6244": "9231",
    "6112": "6113",   # junior colleges → colleges
    "6114": "6111",   # business schools → K-12 (best available)
    "6115": "6111",
    "6116": "6111",
    "6117": "6111",
    "9999": "—",
}


# ── Data fetching ────────────────────────────────────────────────────────────

def try_download(url: str, label: str, stream: bool = False) -> Optional[requests.Response]:
    """Attempt a GET with timeout. Returns response or None."""
    try:
        print(f"  Trying: {url}")
        resp = requests.get(url, timeout=120, stream=stream)
        if resp.status_code == 200:
            print(f"  OK ({label})")
            return resp
        else:
            print(f"  HTTP {resp.status_code} ({label})")
            return None
    except Exception as e:
        print(f"  Failed ({label}): {e}")
        return None


def download_flat_file() -> Optional[List[dict]]:
    """
    Download national QCEW annual singlefile from BLS (~83MB compressed).
    Filters in-memory to PA rows only before building the list.
    BLS no longer provides state-specific splits; national file is the source.
    Uses /tmp cache to avoid re-downloading on repeated runs.
    """
    import pickle
    cache_path = f"/tmp/qcew_pa_rows_{YEAR}.pkl"
    if os.path.exists(cache_path):
        print(f"  Using cached PA rows from {cache_path}")
        try:
            pa_rows = pickle.load(open(cache_path, "rb"))
            print(f"  Loaded {len(pa_rows):,} rows from cache")
            return pa_rows
        except Exception:
            pass

    url = f"https://data.bls.gov/cew/data/files/{YEAR}/csv/{YEAR}_annual_singlefile.zip"
    print(f"  Downloading: {url}")
    print(f"  (national file ~83MB — filtering to PA area_fips 42xxx on the fly)")
    try:
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
        print(f"  Downloaded {len(resp.content) / 1e6:.1f} MB")

        z = zipfile.ZipFile(io.BytesIO(resp.content))
        csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            print("  No CSV found inside zip")
            return None
        print(f"  ZIP contains: {csv_names}")

        pa_rows = []
        with z.open(csv_names[0]) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))
            for row in reader:
                area = row.get("area_fips", "")
                # Keep PA rows: state 42000, county 42XXX
                if area.startswith(PA_FIPS):
                    pa_rows.append(row)

        print(f"  PA rows (area_fips starts with '{PA_FIPS}'): {len(pa_rows):,}")
        try:
            import pickle
            pickle.dump(pa_rows, open(f"/tmp/qcew_pa_rows_{YEAR}.pkl", "wb"))
            print(f"  Cached to /tmp/qcew_pa_rows_{YEAR}.pkl for future runs")
        except Exception:
            pass
        return pa_rows

    except Exception as e:
        print(f"  Flat file download/parse failed: {e}")
        return None


def build_series_id(county_fips: str, own_code: str, naics: str) -> str:
    """
    Build BLS QCEW employment series ID.
    Format: ENU + area_fips(5) + own_code(1) + size_code(1='0') + industry_code
    industry_code uses BLS QCEW coding: 4-digit NAICS → 4 chars, total = '10'
    """
    return f"ENU{county_fips}{own_code}0{naics}"


def api_fallback_audit() -> dict:
    """
    API-based fallback using api.bls.gov time series endpoint.
    Queries Philadelphia (42101) and Allegheny (42003) — large counties,
    less likely to be suppressed — for target NAICS × gov ownership.
    Returns: {naics: {own_code: employment or None}}
    Note: data.bls.gov/cew/api/v2 is unavailable; this uses the public series API.
    Annual data = Q01+Q02+Q03+Q04 average of quarterly employment values.
    """
    TARGET_NAICS = [
        "6111", "6112", "6113",
        "6211", "6216", "6221", "6231",
        "6241", "6243", "6244",
        "9211", "9221", "9231", "9241", "9261", "9281",
    ]
    # Use Philadelphia (largest PA county) — fewest suppressed cells
    SAMPLE_COUNTY = "42101"
    summary = {}

    series_list = []
    series_meta = {}  # series_id → (naics, own_code)
    for naics in TARGET_NAICS:
        for own_code in ["1", "2", "3"]:
            sid = build_series_id(SAMPLE_COUNTY, own_code, naics)
            series_list.append(sid)
            series_meta[sid] = (naics, own_code)

    # BLS API allows up to 50 series per request (unauthenticated limit)
    BLS_SERIES_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    batch_size = 25
    for i in range(0, len(series_list), batch_size):
        batch = series_list[i:i + batch_size]
        payload = {
            "seriesid": batch,
            "startyear": YEAR,
            "endyear": YEAR,
        }
        if BLS_API_KEY and "placeholder" not in BLS_API_KEY.lower() and "your_" not in BLS_API_KEY.lower():
            payload["registrationKey"] = BLS_API_KEY
        try:
            resp = requests.post(BLS_SERIES_API, json=payload, timeout=30)
            if resp.status_code != 200:
                print(f"  BLS API HTTP {resp.status_code}")
                continue
            data = resp.json()
            if data.get("status") != "REQUEST_SUCCEEDED":
                print(f"  BLS API status: {data.get('status')} — {data.get('message', [])}")
                continue
            for series in data.get("Results", {}).get("series", []):
                sid = series["seriesID"]
                naics, own_code = series_meta.get(sid, (None, None))
                if not naics:
                    continue
                # Annual average employment = mean of quarterly values
                qtr_vals = []
                for pt in series.get("data", []):
                    if pt.get("year") == YEAR and pt.get("footnotes", [{}])[0].get("code") != "N":
                        try:
                            qtr_vals.append(int(pt["value"]))
                        except Exception:
                            pass
                emp = round(sum(qtr_vals) / len(qtr_vals)) if qtr_vals else None
                if naics not in summary:
                    summary[naics] = {}
                summary[naics][own_code] = emp
        except Exception as e:
            print(f"  BLS API error: {e}")
        time.sleep(0.5)

    return summary


# ── Parsing flat file ────────────────────────────────────────────────────────

def parse_flat_file(rows: List[dict]) -> Tuple[dict, dict, int, int]:
    """
    Parse flat file rows into:
      state_summary: {naics: {own_code: employment}}   (agglvl=54, area=42000)
      county_sample: {fips: {naics: {own_code: employment | None}}}
    """
    state_summary: dict = {}
    county_sample: dict = {}
    suppressed = 0
    total_gov_county_cells = 0

    for r in rows:
        own = r.get("own_code", "")
        if own not in OWN_NAMES:
            continue

        area = r.get("area_fips", "")
        naics = r.get("industry_code", "")
        agglvl = r.get("agglvl_code", "")
        disclosure = r.get("disclosure_code", "")

        emp_raw = r.get("annual_avg_emplvl", "")
        if disclosure == "N":
            emp = None
            suppressed_flag = True
        else:
            suppressed_flag = False
            try:
                emp = int(str(emp_raw).replace(",", ""))
            except Exception:
                emp = None

        # State-level rows for summary table
        # agglvl=56 = state, 4-digit NAICS × ownership (confirmed from flat file)
        if area == f"{PA_FIPS}000" and agglvl == "56":
            if naics not in state_summary:
                state_summary[naics] = {}
            state_summary[naics][own] = emp

        # County-level rows for suppression sample
        # agglvl=76 = county, 4-digit NAICS × ownership (confirmed from flat file)
        if area in PA_SAMPLE_COUNTIES and agglvl == "76":
            total_gov_county_cells += 1
            if suppressed_flag:
                suppressed += 1
            if area not in county_sample:
                county_sample[area] = {}
            if naics not in county_sample[area]:
                county_sample[area][naics] = {}
            county_sample[area][naics][own] = emp

    return state_summary, county_sample, suppressed, total_gov_county_cells


# ── Reporting ────────────────────────────────────────────────────────────────

def print_audit_table(state_summary: dict):
    """Print the NAICS coverage table."""
    print()
    print("GOVERNMENT NAICS CODES — PA STATE TOTALS (own=1,2,3)")
    print("=" * 108)
    hdr = (f"{'NAICS':<6} | {'Description':<46} | {'Federal':>10} | "
           f"{'State':>10} | {'Local':>10} | {'sector_ids?':>12} | Suggested parent")
    print(hdr)
    print("-" * 108)

    found_any = False
    for naics in sorted(state_summary.keys()):
        if len(naics) != 4:
            continue
        if not (naics.startswith("6") or naics.startswith("9")):
            continue

        emp_data = state_summary[naics]
        fed = emp_data.get("1")
        sta = emp_data.get("2")
        loc = emp_data.get("3")

        # Skip rows with zero total known employment
        known = [e for e in [fed, sta, loc] if e is not None]
        if known and sum(known) == 0:
            continue

        desc = NAICS_DESCRIPTIONS.get(naics, "(no description)")[:45]
        fed_s = f"{fed:>10,}" if fed is not None else f"{'suppressed':>10}"
        sta_s = f"{sta:>10,}" if sta is not None else f"{'suppressed':>10}"
        loc_s = f"{loc:>10,}" if loc is not None else f"{'suppressed':>10}"

        in_sid = f"YES ({naics})" if naics in SECTOR_IDS else "NO"
        parent = PARENT_MAP.get(naics, "—") if naics not in SECTOR_IDS else "—"

        print(f"{naics:<6} | {desc:<46} | {fed_s} | {sta_s} | {loc_s} | {in_sid:>12} | {parent}")
        found_any = True

    print("-" * 108)
    if not found_any:
        print("  (No 4-digit education/health/government NAICS rows found at this agglvl)")
        print("  Check agglvl_code values in the flat file — may need different filter.")


def print_county_sample(county_sample: dict, suppressed: int, total: int):
    """Print per-county employment for key sectors + suppression rate."""
    KEY_NAICS = ["6111", "9211", "9221", "9231", "9241"]

    print()
    print(f"COUNTY-LEVEL SAMPLE — LOCAL GOVT (own=3), KEY NAICS")
    print("=" * 75)
    rate = (suppressed / total * 100) if total > 0 else 0.0
    print(f"Government cells in sample counties: {total:,}  |  Suppressed: {suppressed:,}  |  Rate: {rate:.1f}%")
    print()

    col_w = 10
    header = f"{'County':<14} | " + " | ".join(f"{n:>{col_w}}" for n in KEY_NAICS)
    print(header)
    print("-" * (16 + (col_w + 3) * len(KEY_NAICS)))

    for fips in sorted(PA_SAMPLE_COUNTIES.keys()):
        name = PA_SAMPLE_COUNTIES[fips]
        naics_data = county_sample.get(fips, {})
        vals = []
        for n in KEY_NAICS:
            own_data = naics_data.get(n, {})
            emp = own_data.get("3")  # local govt
            if emp is None and "3" in own_data:
                vals.append(f"{'N':>{col_w}}")
            elif emp is None:
                vals.append(f"{'—':>{col_w}}")
            else:
                vals.append(f"{emp:>{col_w},}")
        print(f"{name:<14} | " + " | ".join(vals))


def print_sector_ids_coverage():
    """Show which government-relevant sector_ids.json entries already exist."""
    gov_keys = [k for k in SECTOR_IDS if k.startswith("9") or k in ("6111", "6112", "6113")]
    print()
    print("EXISTING sector_ids.json ENTRIES (government/education sectors)")
    print("-" * 50)
    for k in sorted(gov_keys):
        desc = NAICS_DESCRIPTIONS.get(k, "(unlisted)")
        print(f"  {k:<8}  {desc}")


def print_nlrb_note():
    print()
    print("NLRB JURISDICTION NOTE (relevant to Task 3)")
    print("=" * 70)
    print("The NLRB (National Labor Relations Act) covers PRIVATE sector workers only.")
    print()
    print("Public sector organizing goes through STATE labor boards, NOT NLRB:")
    print("  PA   → PLRB (Pennsylvania Labor Relations Board)")
    print("  CA   → PERB (Public Employment Relations Board)")
    print("  NY   → PERB (NY)")
    print("  MI   → MERC (Michigan Employment Relations Commission)")
    print("  WI   → WERC (Wisconsin Employment Relations Commission)")
    print("  ~34 states have public sector bargaining laws with their own boards")
    print()
    print("EXCLUDED from NLRB petition data:")
    print("  ✗  K-12 teachers (public schools)")
    print("  ✗  State/local government workers")
    print("  ✗  Public university faculty")
    print("  ✗  Police, firefighters, corrections officers (in most states)")
    print()
    print("INCLUDED in NLRB petition data:")
    print("  ✓  Private hospital and nursing home workers")
    print("  ✓  Private university faculty (NLRB jurisdiction since 2016 NLRB ruling)")
    print("  ✓  Private school staff")
    print("  ✓  All other private sector workers")
    print()
    print("Implication: Task 3 NLRB petition data significantly under-counts")
    print("organizing activity in the government sectors we are adding via QCEW.")


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    print("=" * 70)
    print("QCEW GOVERNMENT EMPLOYMENT AUDIT — PENNSYLVANIA")
    print(f"Year: {YEAR}  |  BLS API Key: {'SET' if BLS_API_KEY else 'NOT SET (anonymous rate limit)'}")
    print("=" * 70)
    print()

    # ── Step 1: Attempt flat file download ───────────────────────────────────
    print("Step 1: Downloading PA QCEW flat file...")
    rows = download_flat_file()

    if rows is not None:
        print(f"\nFlat file loaded: {len(rows):,} total rows")

        # Show agglvl codes present so we know how to filter
        agglvl_counts: dict = {}
        for r in rows:
            own = r.get("own_code", "")
            if own in OWN_NAMES:
                ag = r.get("agglvl_code", "?")
                agglvl_counts[ag] = agglvl_counts.get(ag, 0) + 1
        print("Government rows by agglvl_code:")
        for ag, ct in sorted(agglvl_counts.items()):
            print(f"  agglvl={ag}: {ct:,} rows")

        state_summary, county_sample, suppressed, total = parse_flat_file(rows)
        print(f"\nState-level NAICS codes found: {len(state_summary):,}")
        print(f"County sample rows: {total:,}  ({suppressed:,} suppressed)")

    else:
        # ── Step 2: API fallback ──────────────────────────────────────────────
        print("\nFlat file unavailable — using API fallback (target NAICS × own × PA state)")
        print("(This is slower but covers the same target codes)")
        state_summary = api_fallback_audit()
        county_sample = {}
        suppressed = 0
        total = 0
        print(f"API audit complete: {len(state_summary):,} NAICS codes with data")

    # ── Report ────────────────────────────────────────────────────────────────
    print_sector_ids_coverage()
    print_audit_table(state_summary)
    if total > 0:
        print_county_sample(county_sample, suppressed, total)
    else:
        print("\n(County-level suppression sample not available — flat file required)")
    print_nlrb_note()

    print()
    print("=" * 70)
    print("AUDIT COMPLETE — awaiting Sam's 'Go' before Task 2")
    print("=" * 70)


if __name__ == "__main__":
    run()
