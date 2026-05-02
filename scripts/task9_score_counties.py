"""
Task 9: Calculate Strategic Terrain Scores for all 3,143 counties.
Reads from COUNTIES, EMPLOYMENT, UNIONS, SECTORS, and STATES tables,
computes component scores + final weighted score, then updates COUNTIES
and writes data/county_scores[_test].json.

Usage:
    python task9_score_counties.py --config ../config.json [--dry-run] [--test] [--fips 42101]
"""

import json
import logging
import argparse
import random
import time
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


# ── Component scoring functions ─────────────────────────────────────────────

def score_sectoral_value(employment_by_sector_id: dict[str, float],
                         sector_svs_by_id: dict[str, float]) -> float:
    """
    0–100: SVS-weighted employment scaled to absolute benchmark.
    10,000,000 SVS-weighted worker-points = score of 100.
    """
    total = 0.0
    for sector_id, emp in employment_by_sector_id.items():
        svs = sector_svs_by_id.get(sector_id, 0.0)
        total += emp * svs
    return min(100.0, round(total / 100_000, 2))


def score_organizing_potential(unorganized_workers: int, sector_mix: dict[str, float],
                               rtw: bool) -> int:
    """0–100: workforce size × sector quality × legal environment."""
    # Part A: Unorganized workforce size (0–40)
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

    # Part B: Sector mix quality — healthcare/education/logistics share (0–30)
    healthcare = sector_mix.get("Healthcare", 0)
    education = sector_mix.get("Education", 0)
    logistics = sector_mix.get("Logistics", 0)
    total = sum(sector_mix.values()) or 1
    b = min(30, round(
        (healthcare / total * 15) +
        (education / total * 10) +
        (logistics / total * 10)
    ))

    # Part C: Legal environment (0–30)
    c = 5 if rtw else 30

    return min(100, a + b + c)


def score_presidential(margin: Optional[float], state_abbr: str) -> int:
    """
    0–100: swing-state presidential/federal race relevance.
    NOTE: Does NOT proxy for gubernatorial or Senate races — those trigger
    different organizing interventions even in the same state.
    """
    if margin is None:
        return 20

    abs_margin = abs(margin)

    # Part A: Swing state status (0–50)
    if state_abbr in SWING_STATES:
        a = 50
    elif abs_margin <= 5:
        a = 35
    elif abs_margin <= 10:
        a = 25
    elif abs_margin <= 15:
        a = 15
    else:
        a = 5

    # Part B: County-level competitiveness (0–50)
    if abs_margin <= 5:
        b = 50
    elif abs_margin <= 10:
        b = 35
    elif abs_margin <= 15:
        b = 20
    elif abs_margin <= 20:
        b = 10
    else:
        b = 5

    return min(100, a + b)


def score_statewide(state_margin: Optional[float], county_margin: Optional[float]) -> int:
    """
    0–100: general statewide electoral competitiveness.

    This score applies to all statewide races but must be interpreted differently
    depending on the target office. Presidential, gubernatorial, and Senate races
    each trigger different organizing interventions even in the same state.
    Cycle-specific Senate/gubernatorial data is a future refinement.

    Safe Dem states get a +20 bonus for primary challenge opportunity per
    McAlevey's safe-seat strategy: unions in safe Dem districts have leverage
    over incumbents.
    """
    margin = state_margin if state_margin is not None else county_margin
    if margin is None:
        return 20

    abs_margin = abs(margin)

    if abs_margin <= 3:
        score = 100
    elif abs_margin <= 6:
        score = 80
    elif abs_margin <= 10:
        score = 60
    elif abs_margin <= 15:
        score = 40
    elif abs_margin <= 20:
        score = 20
    else:
        score = 10

    # Safe Dem bonus: margin >= 15 means reliably Democratic
    if margin >= 15:
        score += 20

    return min(100, score)


def score_congressional(margin: Optional[float], trifecta: Optional[str]) -> int:
    """
    0–100: House district and state legislative competitiveness.

    Uses county-level presidential margin as a proxy for district competitiveness.
    Actual Cook Political Report district ratings are a future data addition.
    """
    if margin is None:
        return 20

    abs_margin = abs(margin)

    if abs_margin <= 3:
        score = 100
    elif abs_margin <= 7:
        score = 80
    elif abs_margin <= 12:
        score = 60
    elif abs_margin <= 18:
        score = 40
    elif abs_margin <= 25:
        score = 20
    else:
        score = 10

    # Divided trifecta bonus: state legislature is genuinely in play
    if trifecta == "Divided":
        score += 15

    return min(100, score)


def electoral_composite(presidential: int, statewide: int, congressional: int) -> float:
    return round((presidential * 0.4) + (statewide * 0.3) + (congressional * 0.3), 2)


def score_organized_scale(total_members: int, union_count: int) -> int:
    """0–100: raw scale of existing union presence for political deployment."""
    if total_members >= 100_000:
        return 100
    elif total_members >= 50_000:
        return 80
    elif total_members >= 25_000:
        return 60
    elif total_members >= 10_000:
        return 40
    elif total_members >= 5_000:
        return 20
    elif total_members >= 1_000:
        return 10
    else:
        return min(100, max(0, union_count * 3))


def score_union_culture(total_members: int, total_workforce: int) -> int:
    """0–100: depth of union penetration — how normalized collective action is."""
    density = total_members / total_workforce if total_workforce > 0 else 0.0

    if density >= 0.30:
        return 100
    elif density >= 0.20:
        return 80
    elif density >= 0.12:
        return 60
    elif density >= 0.07:
        return 40
    elif density >= 0.03:
        return 20
    else:
        return 5


def infrastructure_composite(organized_scale: int, union_culture: int) -> float:
    return round((organized_scale * 0.6) + (union_culture * 0.4), 2)


def strategic_terrain_score(electoral: float, org: int, sect: float, infra: float) -> float:
    return round(
        (electoral * 0.35) + (org * 0.30) + (sect * 0.25) + (infra * 0.10),
        2,
    )


def priority_tier(score: float) -> str:
    if score >= 70:
        return "A: High Priority"
    elif score >= 50:
        return "B: Medium Priority"
    return "C: Lower Priority"


def score_organizing_opportunity(sectoral: float, org: int) -> float:
    """
    0–100: PRIMARY OUTPUT — how favorable is terrain for building worker power?
    Independent of electoral considerations. Use this when the question is
    "where is the opportunity?" before filtering by electoral goal.
    """
    return round((sectoral * 0.55) + (org * 0.45), 2)


def classify_intervention(infra: float, electoral: float, statewide: int) -> str:
    """
    Categorical intervention type — not a score.
    Type A: Organize Unorganized — low infrastructure, needs new campaigns.
    Type B: Political Activation — unions present but not politically engaged.
    Type C: Partnership — activated unions to coordinate with, not build.
    """
    if infra < 30:
        return "Type A: Organize Unorganized"
    elif infra >= 30 and electoral >= 50:
        if statewide < 50:
            return "Type B: Political Activation"
        else:
            return "Type C: Partnership"
    else:
        return "Type B: Political Activation"


# ── Property extraction helper ─────────────────────────────────────────────

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


# ── Main ───────────────────────────────────────────────────────────────────

def run(config_path: str, dry_run: bool = False, single_fips: Optional[str] = None,
        test_mode: bool = False):
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
    sector_type_by_id: dict[str, str] = {}
    sector_name_by_id: dict[str, str] = {}
    sector_svs_by_id: dict[str, float] = {}
    for s in sectors_raw:
        sid = s["id"]
        sector_type_by_id[sid] = get_prop(s, "Sector Type", "select") or "Other"
        sector_name_by_id[sid] = get_prop(s, "Sector Name", "title") or ""
        svs = get_prop(s, "Strategic Value Score", "number")
        sector_svs_by_id[sid] = float(svs) if svs is not None else 0.0

    # ── Pre-load STATES ────────────────────────────────────────────────────
    logger.info("Pre-loading states from Notion")
    states_raw = client.query_all(db["states"])
    state_margin_by_abbr: dict[str, float] = {}
    state_trifecta_by_abbr: dict[str, str] = {}
    for st in states_raw:
        abbr = get_prop(st, "State Abbr", "text") or ""
        margin = get_prop(st, "Presidential 2024 Margin", "number")
        trifecta = get_prop(st, "Trifecta", "select")
        if abbr:
            if margin is not None:
                state_margin_by_abbr[abbr] = float(margin)
            if trifecta:
                state_trifecta_by_abbr[abbr] = trifecta

    # ── Load counties ─────────────────────────────────────────────────────
    logger.info("Fetching all counties from Notion")
    all_counties = client.query_all(db["counties"])

    if single_fips:
        all_counties = [
            c for c in all_counties
            if get_prop(c, "FIPS Code", "text") == single_fips
        ]
    elif test_mode:
        # Top 200 by population + 200 random from the rest
        priority_fips = set(config["priority_counties"]["phase_1_top_100"])
        # Sort all by population descending; use priority list as guaranteed top-tier anchor,
        # then fill to 200 from remaining sorted by population
        def pop(c):
            return get_prop(c, "Population", "number") or 0

        sorted_all = sorted(all_counties, key=pop, reverse=True)
        top200 = sorted_all[:200]
        top200_ids = {c["id"] for c in top200}
        rest = [c for c in all_counties if c["id"] not in top200_ids]
        random.seed(42)
        random200 = random.sample(rest, min(200, len(rest)))
        all_counties = top200 + random200
        logger.info(
            f"TEST MODE: top 200 by population + {len(random200)} random = {len(all_counties)} counties"
        )

    logger.info(f"Processing {len(all_counties)} counties")

    scored_records: list[dict] = []
    dist_a = dist_b = dist_c = 0
    type_a = type_b = type_c = 0

    for i, county in enumerate(all_counties, 1):
        county_id = county["id"]
        fips = get_prop(county, "FIPS Code", "text") or ""
        county_name = get_prop(county, "County Name", "title") or get_prop(county, "Name", "title") or ""
        state_abbr = FIPS_TO_STATE.get(fips[:2], "")
        margin_2024 = get_prop(county, "Presidential 2024 Margin", "number")
        population = get_prop(county, "Population", "number") or 0
        rural_urban = get_prop(county, "Rural-Urban Classification", "select") or \
                      get_prop(county, "Rural Urban", "select") or ""
        region = get_prop(county, "Region", "select") or ""

        in_swing = state_abbr in SWING_STATES
        state_info = density_data["states"].get(state_abbr, {})
        rtw = state_info.get("right_to_work", False)
        state_margin = state_margin_by_abbr.get(state_abbr)
        trifecta = state_trifecta_by_abbr.get(state_abbr)

        # ── Employment records ────────────────────────────────────────────
        emp_records = client.query_all(
            db["employment"],
            {"property": "County", "relation": {"contains": county_id}},
        )

        total_unorganized = 0
        total_workforce = 0
        employment_by_sector_id: dict[str, float] = {}
        sector_mix: dict[str, float] = {}

        for emp in emp_records:
            emp_total = get_prop(emp, "Total Employment", "number") or 0
            emp_union = get_prop(emp, "Estimated Union Members", "number") or 0
            total_workforce += emp_total
            total_unorganized += max(0, emp_total - emp_union)

            for sid in (get_prop(emp, "Sector", "relation") or []):
                employment_by_sector_id[sid] = employment_by_sector_id.get(sid, 0.0) + emp_total
                stype = sector_type_by_id.get(sid, "Other")
                sector_mix[stype] = sector_mix.get(stype, 0.0) + emp_total

        if not emp_records:
            # CBP excludes government employers, so public-sector-heavy counties
            # will show zero here — sectoral/organizing scores will be understated.
            logger.debug(f"{fips}: no employment records — sectoral/organizing scores will be 0")

        # ── Union records ─────────────────────────────────────────────────
        union_records = client.query_all(
            db["unions"],
            {"property": "Primary County", "relation": {"contains": county_id}},
        )
        union_count = len(union_records)
        total_members = 0
        for u in union_records:
            m = get_prop(u, "Total Members", "number")
            if m is not None:
                total_members += int(m)

        # ── Scores ────────────────────────────────────────────────────────
        # PRIMARY OUTPUTS (what the dashboard surfaces by default)
        # - organizing_opportunity_score: how favorable is terrain for building power?
        # - intervention_type: what kind of resources does this place need?
        #
        # ELECTORAL FILTERING (user applies based on their strategic goal)
        # - presidential_score: use when goal = presidential election
        # - statewide_score: use when goal = governor / long-term state transformation
        # - congressional_score: use when goal = flip the House
        #
        # REFERENCE ONLY (stored but not primary)
        # - terrain_score: legacy composite, kept for continuity
        # - priority_tier: deprecated A/B/C, kept for reference

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

        if dry_run:
            logger.info(
                f"{fips} {state_abbr} | OPP={opp:.1f} [{intervention}] | "
                f"P={pres} SW={statewide} CG={congressional} E={electoral:.1f} | "
                f"O={org} S={sectoral:.1f} OS={org_scale} UC={union_culture} I={infra:.1f} | "
                f"terrain={terrain} ({tier})"
            )
            continue

        try:
            client.update_page(county_id, update_props)
            if i % 100 == 0:
                logger.info(f"Scored {i}/{len(all_counties)} counties")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed update for {fips}: {e}")

    # ── Write county_scores.json ──────────────────────────────────────────
    output_dir = Path(config_path).parent / "data"
    output_dir.mkdir(exist_ok=True)
    filename = "county_scores_test.json" if test_mode else "county_scores.json"
    output_path = output_dir / filename
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fips", help="Score only one county (for debugging)")
    parser.add_argument(
        "--test", action="store_true",
        help="Score top 200 by population + 200 random (seed=42); writes county_scores_test.json"
    )
    args = parser.parse_args()
    run(args.config, args.dry_run, args.fips, args.test)
