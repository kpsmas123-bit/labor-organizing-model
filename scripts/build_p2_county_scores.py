"""
Terrain v2.0 — P2 County Alignment Score Builder

Maps legislator-level key_vote_scores from federal_key_vote_scores.csv
to county FIPS codes using two methods:

  House members  → district_county_crosswalk.csv (geographic overlap weights)
  Senate members → equal weight across all counties in the senator's state
                   (approximation; population-weighted version deferred to Phase 4C
                    pending census population data)

Output: data/processed/p2_county_alignment.csv

Columns:
  fips, county_name, state_fips, state,
  key_vote_score, legislator_count, coverage_type

coverage_type values:
  "house_and_senate" — county has both House and Senate score contributions
  "senate_only"      — county's House rep(s) had no score (e.g. not in vote data)
  "house_only"       — no Senate data for this state (should not occur)

Usage:
  python scripts/build_p2_county_scores.py

Reads:
  data/processed/federal_key_vote_scores.csv
  data/processed/district_county_crosswalk.csv
Writes:
  data/processed/p2_county_alignment.csv
"""

import csv
import logging
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
SCORES_CSV = REPO_ROOT / "data" / "processed" / "federal_key_vote_scores.csv"
CROSSWALK_CSV = REPO_ROOT / "data" / "processed" / "district_county_crosswalk.csv"

# Use the main repo's crosswalk if the worktree doesn't have one
if not CROSSWALK_CSV.exists():
    CROSSWALK_CSV = REPO_ROOT.parent.parent.parent / "data" / "processed" / "district_county_crosswalk.csv"

OUTPUT_CSV = REPO_ROOT / "data" / "processed" / "p2_county_alignment.csv"

OUTPUT_FIELDS = [
    "fips", "state_fips", "state",
    "key_vote_score", "legislator_count", "coverage_type",
]

# 2-letter state abbreviation → 2-digit FIPS code
STATE_ABBR_TO_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
    "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
    "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
    "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
    "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
    "DC": "11",
}


def load_scores() -> tuple[list[dict], list[dict]]:
    """Load federal_key_vote_scores.csv; split into House and Senate lists."""
    house, senate = [], []
    with open(SCORES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            score = row.get("key_vote_score", "")
            if score == "" or score == "None":
                continue  # member abstained on all tracked votes — exclude
            row["key_vote_score"] = float(score)
            if row["chamber"] == "house":
                house.append(row)
            elif row["chamber"] == "senate":
                senate.append(row)
    log.info("Loaded %d House and %d Senate scored members", len(house), len(senate))
    return house, senate


def load_crosswalk() -> dict[tuple[str, str], list[tuple[str, float]]]:
    """
    Load district_county_crosswalk.csv.

    Returns dict keyed by (state_fips, district_number) →
    list of (county_fips, overlap_weight) tuples.
    """
    cw: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    with open(CROSSWALK_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["district_state"], row["district_number"])
            cw[key].append((row["county_fips"], float(row["overlap_weight"])))
    log.info("Loaded crosswalk: %d unique districts", len(cw))
    return cw


def build_county_scores(
    house_members: list[dict],
    senate_members: list[dict],
    crosswalk: dict[tuple[str, str], list[tuple[str, float]]],
) -> dict[str, dict]:
    """
    Aggregate member key_vote_scores to county FIPS codes.

    Each county accumulates a weighted-average score from:
      - House members whose districts overlap the county (weight = overlap_weight)
      - Senate members from the county's state (weight = 1 / n_counties_in_state)

    Returns dict keyed by county_fips → aggregation dict.
    """
    # county_fips → {"weighted_score_sum": float, "weight_sum": float,
    #                "legislator_count": int, "has_house": bool, "has_senate": bool,
    #                "state_fips": str, "state": str}
    county: dict[str, dict] = {}

    def ensure(fips: str, state_fips: str, state_abbr: str) -> None:
        if fips not in county:
            county[fips] = {
                "weighted_score_sum": 0.0,
                "weight_sum": 0.0,
                "legislator_count": 0,
                "has_house": False,
                "has_senate": False,
                "state_fips": state_fips,
                "state": state_abbr,
            }

    # --- House contributions ---
    house_skipped = 0
    for m in house_members:
        state_abbr = m["state"].upper()
        state_fips = STATE_ABBR_TO_FIPS.get(state_abbr, "")
        district = m.get("district", "")

        if not state_fips or not district:
            house_skipped += 1
            continue

        counties_for_district = crosswalk.get((state_fips, district), [])
        if not counties_for_district:
            house_skipped += 1
            continue

        score = m["key_vote_score"]
        for county_fips, overlap_weight in counties_for_district:
            ensure(county_fips, state_fips, state_abbr)
            county[county_fips]["weighted_score_sum"] += score * overlap_weight
            county[county_fips]["weight_sum"] += overlap_weight
            county[county_fips]["legislator_count"] += 1
            county[county_fips]["has_house"] = True

    if house_skipped:
        log.warning("%d House members skipped (missing state_fips or district or crosswalk entry)", house_skipped)

    # --- Senate contributions (equal weight per county within state) ---
    # First: build state → list of county_fips from the crosswalk
    state_counties: dict[str, set[str]] = defaultdict(set)
    for (state_fips, _), county_list in crosswalk.items():
        for county_fips, _ in county_list:
            state_counties[state_fips].add(county_fips)

    senate_skipped = 0
    for m in senate_members:
        state_abbr = m["state"].upper()
        state_fips = STATE_ABBR_TO_FIPS.get(state_abbr, "")
        if not state_fips:
            senate_skipped += 1
            continue

        counties_in_state = state_counties.get(state_fips, set())
        if not counties_in_state:
            senate_skipped += 1
            continue

        score = m["key_vote_score"]
        equal_weight = 1.0 / len(counties_in_state)

        for county_fips in counties_in_state:
            sf = STATE_ABBR_TO_FIPS.get(state_abbr, state_fips)
            ensure(county_fips, sf, state_abbr)
            county[county_fips]["weighted_score_sum"] += score * equal_weight
            county[county_fips]["weight_sum"] += equal_weight
            county[county_fips]["legislator_count"] += 1
            county[county_fips]["has_senate"] = True

    if senate_skipped:
        log.warning("%d Senate members skipped (missing state_fips or no counties)", senate_skipped)

    return county


def finalize_scores(county: dict[str, dict]) -> list[dict]:
    """Convert raw accumulator dict to output rows."""
    rows = []
    for fips, c in sorted(county.items()):
        if c["weight_sum"] == 0:
            continue
        score = round(c["weighted_score_sum"] / c["weight_sum"], 4)

        if c["has_house"] and c["has_senate"]:
            coverage = "house_and_senate"
        elif c["has_senate"]:
            coverage = "senate_only"
        else:
            coverage = "house_only"

        rows.append({
            "fips": fips,
            "state_fips": c["state_fips"],
            "state": c["state"],
            "key_vote_score": score,
            "legislator_count": c["legislator_count"],
            "coverage_type": coverage,
        })
    return rows


def print_spot_checks(rows: list[dict]) -> None:
    """Report scores for five specified spot-check counties."""
    targets = {
        "42101": "Philadelphia PA",
        "42027": "Centre County PA",
        "55045": "Green County WI",
        "06037": "LA County CA",
        "04013": "Maricopa County AZ",
    }
    idx = {r["fips"]: r for r in rows}
    print("\n=== SPOT CHECKS ===")
    for fips, label in targets.items():
        if fips in idx:
            r = idx[fips]
            print(
                f"  {label} ({fips}): score={r['key_vote_score']:.4f}  "
                f"legislators={r['legislator_count']}  coverage={r['coverage_type']}"
            )
        else:
            print(f"  {label} ({fips}): NOT IN OUTPUT")


def main() -> None:
    house, senate = load_scores()
    crosswalk = load_crosswalk()

    county_accum = build_county_scores(house, senate, crosswalk)
    rows = finalize_scores(county_accum)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    log.info("Wrote %d county rows → %s", len(rows), OUTPUT_CSV)

    n_both = sum(1 for r in rows if r["coverage_type"] == "house_and_senate")
    n_senate = sum(1 for r in rows if r["coverage_type"] == "senate_only")
    n_house = sum(1 for r in rows if r["coverage_type"] == "house_only")
    log.info("Coverage: house_and_senate=%d  senate_only=%d  house_only=%d", n_both, n_senate, n_house)

    print_spot_checks(rows)


if __name__ == "__main__":
    main()
