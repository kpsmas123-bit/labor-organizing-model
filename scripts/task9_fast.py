"""
Task 9 (fast): Calculate Strategic Terrain Scores for all 3,143 counties.

Optimizations over task9_score_counties.py:
  - Bulk-loads union records (fits under Notion 10K cap).
  - Parallel employment queries using ThreadPoolExecutor (2 workers).
  - --json-only: write county_scores.json without touching Notion (fast pass).

Usage:
    python task9_fast.py --config ../config.json --json-only
    python task9_fast.py --config ../config.json          # full run with Notion writes
    python task9_fast.py --config ../config.json --fips 42101
"""

import json
import logging
import argparse
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import NotionClient, number_prop, select_prop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / "logs" / "task9_scoring.log"),
    ],
)
logger = logging.getLogger(__name__)

SWING_STATES = {"AZ", "GA", "MI", "NV", "NC", "PA", "WI"}

FIPS_TO_STATE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY",
}

_progress_lock = threading.Lock()
_progress_counter = [0]


# ── Component scoring functions ─────────────────────────────────────────────

def score_sectoral_value(employment_by_sector_id: dict, sector_svs_by_id: dict) -> float:
    total = 0.0
    for sector_id, emp in employment_by_sector_id.items():
        svs = sector_svs_by_id.get(sector_id, 0.0)
        total += emp * svs
    return min(100.0, round(total / 100_000, 2))


def score_organizing_potential(unorganized_workers: int, sector_mix: dict, rtw: bool) -> int:
    if unorganized_workers >= 100_000:
        a = 40
    elif unorganized_workers >= 50_000:
        a = 30
    elif unorganized_workers >= 25_000:
        a = 20
    elif unorganized_workers >= 10_000:
        a = 10
    else:
        a = 5

    healthcare = sector_mix.get("Healthcare", 0)
    education = sector_mix.get("Education", 0)
    logistics = sector_mix.get("Logistics", 0)
    total = sum(sector_mix.values()) or 1
    b = min(30, round(
        (healthcare / total * 15) +
        (education / total * 10) +
        (logistics / total * 10)
    ))

    c = 5 if rtw else 30
    return min(100, a + b + c)


def score_presidential(margin: Optional[float], state_abbr: str) -> int:
    if margin is None:
        return 20
    abs_margin = abs(margin)
    a = 50 if state_abbr in SWING_STATES else (
        35 if abs_margin <= 5 else
        25 if abs_margin <= 10 else
        15 if abs_margin <= 15 else 5
    )
    b = (50 if abs_margin <= 5 else
         35 if abs_margin <= 10 else
         20 if abs_margin <= 15 else
         10 if abs_margin <= 20 else 5)
    return min(100, a + b)


def score_statewide(state_margin: Optional[float], county_margin: Optional[float]) -> int:
    margin = state_margin if state_margin is not None else county_margin
    if margin is None:
        return 20
    abs_margin = abs(margin)
    score = (100 if abs_margin <= 3 else
             80 if abs_margin <= 6 else
             60 if abs_margin <= 10 else
             40 if abs_margin <= 15 else
             20 if abs_margin <= 20 else 10)
    if margin >= 15:
        score += 20
    return min(100, score)


def score_congressional(margin: Optional[float], trifecta: Optional[str]) -> int:
    if margin is None:
        return 20
    abs_margin = abs(margin)
    score = (100 if abs_margin <= 3 else
             80 if abs_margin <= 7 else
             60 if abs_margin <= 12 else
             40 if abs_margin <= 18 else
             20 if abs_margin <= 25 else 10)
    if trifecta == "Divided":
        score += 15
    return min(100, score)


def electoral_composite(presidential: int, statewide: int, congressional: int) -> float:
    return round((presidential * 0.4) + (statewide * 0.3) + (congressional * 0.3), 2)


def score_organized_scale(total_members: int, union_count: int) -> int:
    if total_members >= 100_000: return 100
    elif total_members >= 50_000: return 80
    elif total_members >= 25_000: return 60
    elif total_members >= 10_000: return 40
    elif total_members >= 5_000: return 20
    elif total_members >= 1_000: return 10
    else: return min(100, max(0, union_count * 3))


def score_union_culture(total_members: int, total_workforce: int) -> int:
    density = total_members / total_workforce if total_workforce > 0 else 0.0
    if density >= 0.30: return 100
    elif density >= 0.20: return 80
    elif density >= 0.12: return 60
    elif density >= 0.07: return 40
    elif density >= 0.03: return 20
    else: return 5


def infrastructure_composite(organized_scale: int, union_culture: int) -> float:
    return round((organized_scale * 0.6) + (union_culture * 0.4), 2)


def strategic_terrain_score(electoral: float, org: int, sect: float, infra: float) -> float:
    return round((electoral * 0.35) + (org * 0.30) + (sect * 0.25) + (infra * 0.10), 2)


def priority_tier(score: float) -> str:
    if score >= 37.0:
        return "A: High Priority"
    elif score >= 19.0:
        return "B: Medium Priority"
    return "C: Lower Priority"


def score_organizing_opportunity(sectoral: float, org: int) -> float:
    return round((sectoral * 0.55) + (org * 0.45), 2)


def classify_intervention(infra: float, electoral: float, statewide: int) -> str:
    if infra < 30:
        return "Type A: Organize Unorganized"
    elif infra >= 30 and electoral >= 50:
        if statewide < 50:
            return "Type B: Political Activation"
        else:
            return "Type C: Partnership"
    else:
        return "Type B: Political Activation"


# ── Property extraction ─────────────────────────────────────────────────────

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


# ── Parallel employment fetch ───────────────────────────────────────────────

def fetch_county_data(client: NotionClient, emp_db_id: str, union_db_id: str,
                       county_id: str, total: int) -> tuple:
    """Returns (county_id, emp_records, union_records). Called from worker threads."""
    try:
        emp_records = client.query_all(
            emp_db_id,
            {"property": "County", "relation": {"contains": county_id}},
        )
    except Exception as e:
        logger.warning(f"Employment query failed for {county_id}: {e}")
        emp_records = []

    try:
        union_records = client.query_all(
            union_db_id,
            {"property": "Primary County", "relation": {"contains": county_id}},
        )
    except Exception as e:
        logger.warning(f"Union query failed for {county_id}: {e}")
        union_records = []

    with _progress_lock:
        _progress_counter[0] += 1
        n = _progress_counter[0]
        if n % 200 == 0:
            logger.info(f"Data prefetch: {n}/{total} counties")

    return (county_id, emp_records, union_records)


# ── Main ────────────────────────────────────────────────────────────────────

def run(config_path: str, dry_run: bool = False, single_fips: Optional[str] = None,
        json_only: bool = False, workers: int = 2):
    config = json.loads(Path(config_path).read_text())
    notion_cfg = config["notion"]
    density_data = json.loads(
        (Path(config_path).parent / "state_union_density.json").read_text()
    )

    client = NotionClient(notion_cfg["api_key"])
    db = notion_cfg["databases"]

    # ── Pre-load SECTORS ──────────────────────────────────────────────────
    logger.info("Pre-loading sectors from Notion")
    sectors_raw = client.query_all(db["sectors"])
    sector_type_by_id: dict = {}
    sector_svs_by_id: dict = {}
    for s in sectors_raw:
        sid = s["id"]
        sector_type_by_id[sid] = get_prop(s, "Sector Type", "select") or "Other"
        svs = get_prop(s, "Strategic Value Score", "number")
        sector_svs_by_id[sid] = float(svs) if svs is not None else 0.0
    logger.info(f"Loaded {len(sectors_raw)} sectors")

    svs_vals = sorted(sector_svs_by_id.values(), reverse=True)
    nonzero = [v for v in svs_vals if v > 0]
    logger.info(
        f"SVS range: {min(svs_vals):.1f}–{max(svs_vals):.1f}, "
        f"nonzero: {len(nonzero)}, top-5: {svs_vals[:5]}"
    )

    # ── Pre-load STATES ────────────────────────────────────────────────────
    logger.info("Pre-loading states from Notion")
    states_raw = client.query_all(db["states"])
    state_margin_by_abbr: dict = {}
    state_trifecta_by_abbr: dict = {}
    for st in states_raw:
        abbr = get_prop(st, "State Abbr", "text") or ""
        margin = get_prop(st, "Presidential 2024 Margin", "number")
        trifecta = get_prop(st, "Trifecta", "select")
        if abbr:
            if margin is not None:
                state_margin_by_abbr[abbr] = float(margin)
            if trifecta:
                state_trifecta_by_abbr[abbr] = trifecta
    logger.info(f"Loaded {len(states_raw)} states")

    # ── Load counties ─────────────────────────────────────────────────────
    logger.info("Fetching all counties from Notion")
    all_counties = client.query_all(db["counties"])
    logger.info(f"Loaded {len(all_counties)} counties")

    if single_fips:
        all_counties = [
            c for c in all_counties
            if get_prop(c, "FIPS Code", "text") == single_fips
        ]

    logger.info(f"Processing {len(all_counties)} counties")

    # ── Parallel employment + union prefetch ──────────────────────────────
    # Both DBs exceed Notion's 10K unfiltered query cap, so we query per
    # county. Thread pool runs employment + union queries together per county.
    logger.info(f"Prefetching employment + union records ({workers} parallel workers)…")
    county_ids = [c["id"] for c in all_counties]
    emp_by_county: dict = {}
    unions_by_county: dict = {}
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                fetch_county_data, client, db["employment"], db["unions"], cid, len(county_ids)
            ): cid
            for cid in county_ids
        }
        for fut in as_completed(futures):
            cid, emp_records, union_records = fut.result()
            emp_by_county[cid] = emp_records
            unions_by_county[cid] = union_records

    elapsed = time.time() - t0
    counties_with_emp = sum(1 for v in emp_by_county.values() if v)
    counties_with_unions = sum(1 for v in unions_by_county.values() if v)
    logger.info(
        f"Prefetch done: emp={counties_with_emp} unions={counties_with_unions} "
        f"counties (elapsed {elapsed/60:.1f} min)"
    )

    # ── Score each county ─────────────────────────────────────────────────
    scored_records: list = []
    dist_a = dist_b = dist_c = 0
    type_a = type_b = type_c = 0
    no_emp_counties = []

    for i, county in enumerate(all_counties, 1):
        county_id = county["id"]
        fips = get_prop(county, "FIPS Code", "text") or ""
        county_name = (get_prop(county, "County Name", "title") or
                       get_prop(county, "Name", "title") or "")
        state_abbr = FIPS_TO_STATE.get(fips[:2], "")
        margin_2024 = get_prop(county, "Presidential 2024 Margin", "number")
        population = get_prop(county, "Population", "number") or 0
        rural_urban = (get_prop(county, "Rural-Urban Classification", "select") or
                       get_prop(county, "Rural Urban", "select") or "")
        region = get_prop(county, "Region", "select") or ""

        in_swing = state_abbr in SWING_STATES
        state_info = density_data["states"].get(state_abbr, {})
        rtw = state_info.get("right_to_work", False)
        state_margin = state_margin_by_abbr.get(state_abbr)
        trifecta = state_trifecta_by_abbr.get(state_abbr)

        emp_records = emp_by_county.get(county_id, [])
        if not emp_records:
            no_emp_counties.append(fips)

        total_unorganized = 0
        total_workforce = 0
        employment_by_sector_id: dict = {}
        sector_mix: dict = {}

        for emp in emp_records:
            emp_total = get_prop(emp, "Total Employment", "number") or 0
            emp_union = get_prop(emp, "Estimated Union Members", "number") or 0
            total_workforce += emp_total
            total_unorganized += max(0, emp_total - emp_union)

            for sid in (get_prop(emp, "Sector", "relation") or []):
                employment_by_sector_id[sid] = employment_by_sector_id.get(sid, 0.0) + emp_total
                stype = sector_type_by_id.get(sid, "Other")
                sector_mix[stype] = sector_mix.get(stype, 0.0) + emp_total

        union_records = unions_by_county.get(county_id) or []
        union_count = len(union_records)
        total_members = 0
        for u in union_records:
            m = get_prop(u, "Total Members", "number")
            if m is not None:
                total_members += int(m)

        sectoral = score_sectoral_value(employment_by_sector_id, sector_svs_by_id)
        org = score_organizing_potential(total_unorganized, sector_mix, rtw)

        pres = score_presidential(margin_2024, state_abbr)
        statewide = score_statewide(state_margin, margin_2024)
        congressional = score_congressional(margin_2024, trifecta)
        electoral = electoral_composite(pres, statewide, congressional)

        org_scale = score_organized_scale(total_members, union_count)
        union_culture = score_union_culture(total_members, total_workforce)
        infra = infrastructure_composite(org_scale, union_culture)

        opp = score_organizing_opportunity(sectoral, org)
        terrain = strategic_terrain_score(electoral, org, sectoral, infra)
        tier = priority_tier(terrain)
        intervention = classify_intervention(infra, electoral, statewide)

        if tier.startswith("A"):
            dist_a += 1
        elif tier.startswith("B"):
            dist_b += 1
        else:
            dist_c += 1

        if intervention.startswith("Type A"):
            type_a += 1
        elif intervention.startswith("Type B"):
            type_b += 1
        else:
            type_c += 1

        scored_records.append({
            "id": county_id,
            "fips": fips,
            "county_name": county_name,
            "state": state_abbr,
            "region": region,
            "population": population,
            "rural_urban": rural_urban,
            "swing_state": in_swing,
            "margin_2024": margin_2024,
            "organizing_opportunity_score": opp,
            "intervention_type": intervention,
            "presidential_score": pres,
            "statewide_score": statewide,
            "congressional_score": congressional,
            "electoral_score": electoral,
            "organizing_score": org,
            "sectoral_score": sectoral,
            "organized_scale_score": org_scale,
            "union_culture_score": union_culture,
            "infra_score": infra,
            "terrain_score": terrain,
            "priority_tier": tier,
        })

        if dry_run or json_only:
            continue

        update_props = {
            "Organizing Opportunity Score": number_prop(opp),
            "Electoral Geography Score": number_prop(electoral),
            "Presidential Score": number_prop(pres),
            "Statewide Score": number_prop(statewide),
            "Congressional Score": number_prop(congressional),
            "Organizing Potential Score": number_prop(org),
            "Sectoral Value Score": number_prop(sectoral),
            "Infrastructure Score": number_prop(infra),
            "Organized Scale Score": number_prop(org_scale),
            "Union Culture Score": number_prop(union_culture),
            "Strategic Terrain Score": number_prop(terrain),
            "Priority Tier": select_prop(tier),
            "Intervention Type": select_prop(intervention),
        }

        try:
            client.update_page(county_id, update_props)
            if i % 100 == 0:
                logger.info(f"Scored + updated {i}/{len(all_counties)} counties")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed update for {fips}: {e}")

    # ── Write county_scores.json ──────────────────────────────────────────
    if not dry_run:
        output_dir = Path(config_path).parent / "data"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "county_scores.json"
        output_path.write_text(json.dumps(scored_records, indent=2))
        logger.info(f"Wrote {len(scored_records)} records to {output_path}")

    # ── Summary ───────────────────────────────────────────────────────────
    total = dist_a + dist_b + dist_c
    logger.info(f"Priority tiers: A={dist_a} B={dist_b} C={dist_c}")
    if total:
        logger.info(
            f"Distribution: {dist_a/total*100:.1f}% A-tier, "
            f"{dist_b/total*100:.1f}% B-tier, "
            f"{dist_c/total*100:.1f}% C-tier"
        )
    logger.info(f"Intervention types: Type A={type_a} Type B={type_b} Type C={type_c}")
    logger.info(f"Counties with no employment records: {len(no_emp_counties)}")
    if no_emp_counties:
        logger.info(f"  First 20: {no_emp_counties[:20]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute scores but skip Notion writes and JSON output")
    parser.add_argument("--json-only", action="store_true",
                        help="Write county_scores.json but skip Notion page updates")
    parser.add_argument("--fips", help="Score only one county")
    parser.add_argument("--workers", type=int, default=2,
                        help="Parallel workers for employment fetch (default 2)")
    args = parser.parse_args()
    run(args.config, args.dry_run, args.fips, args.json_only, args.workers)
