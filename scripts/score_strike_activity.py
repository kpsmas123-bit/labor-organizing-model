"""
P2-1b: Strike Activity Score

Queries STRIKES DB, aggregates by county FIPS, and computes strike_activity_score (0–100)
for each county. Merges result into county_scores.json as a standalone field.

Score is independent — NOT folded into organizing_opportunity_score without explicit approval.

Theoretical basis: Strike activity is the most direct empirical signal of existing worker
militancy and organizational capacity. A county with recent strike history has demonstrated
willingness to take collective action — the hardest quality to predict from structural data.
(McAlevey: organic leadership capacity is best evidenced by observable worker action.)

Coverage caveat: ~89% of counties will have zero strike history in 2019–2024 Cornell data.
Zero = "undemonstrated," not "incapable." Score rewards confirmed capacity; absence is neutral.

Incarcerated worker strikes: Cornell data includes strikes by incarcerated workers (e.g.,
prison labor actions, work stoppages). These are intentionally included — they represent
a form of collective action and worker militancy even if not covered by standard labor law.
Methodology page flags their inclusion explicitly.

Known measurement limitation — multi-site worker counts: Cornell records Workers Involved
as the total for the entire action, then assigns it to the county of the listed location.
For system-wide strikes (UC, Kaiser, airline, etc.) this credits all participants to a
single anchor county rather than distributing workers across locations. Worker counts
should be read as organization-level scale at the anchor location, not distributed
county-level headcount. This overstates absolute worker scale for anchor counties of
large multi-site actions; county strike frequency and recency scores are unaffected.

Usage:
    python score_strike_activity.py --config ../config.json [--dry-run]
"""

import json
import logging
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import date
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent))
from notion_client import NotionClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / "logs" / "score_strike_activity.log"),
    ],
)
logger = logging.getLogger(__name__)


def get_prop(page: dict, prop_name: str, prop_type: str):
    prop = page.get("properties", {}).get(prop_name, {})
    if prop_type == "number":
        return prop.get("number")
    if prop_type == "title":
        lst = prop.get("title", [])
        return lst[0]["text"]["content"] if lst else ""
    if prop_type == "text":
        lst = prop.get("rich_text", [])
        return lst[0]["text"]["content"] if lst else ""
    if prop_type == "relation":
        return [r["id"] for r in prop.get("relation", [])]
    if prop_type == "date":
        d = prop.get("date")
        return d["start"] if d else None
    return None


# ── Scoring functions ──────────────────────────────────────────────────────

def score_frequency(count: int) -> int:
    """0–100: number of distinct strikes in county 2019–2024."""
    if count == 0:    return 0
    if count == 1:    return 15
    if count <= 3:    return 30
    if count <= 6:    return 50
    if count <= 10:   return 70
    if count <= 20:   return 85
    return 100


def score_scale(total_workers: int, has_any_worker_data: bool) -> Optional[int]:
    """
    0–100: total workers involved across all strikes.
    Returns None if no worker data at all for this county (triggers reweighting).
    """
    if not has_any_worker_data:
        return None
    if total_workers <= 0:      return 0
    if total_workers < 500:     return 15
    if total_workers < 2_000:   return 30
    if total_workers < 10_000:  return 50
    if total_workers < 50_000:  return 70
    if total_workers < 200_000: return 85
    return 100


def score_recency(most_recent_year: Optional[int]) -> int:
    """0–100: year of most recent strike in county."""
    if most_recent_year is None: return 0
    if most_recent_year <= 2020: return 25
    if most_recent_year <= 2022: return 50
    if most_recent_year == 2023: return 75
    return 100  # 2024+


def compute_strike_score(freq: int, scale: Optional[int], recency: int) -> float:
    """
    Composite strike_activity_score (0–100).
    When workers data is available: freq×0.40 + scale×0.35 + recency×0.25
    When workers data is absent (Cornell null): freq×0.55 + recency×0.45
    """
    if scale is not None:
        return round(freq * 0.40 + scale * 0.35 + recency * 0.25, 2)
    else:
        return round(freq * 0.55 + recency * 0.45, 2)


# ── Main ─────────────────────────────────────────────────────────────────────

def run(config_path: str, dry_run: bool = False):
    config = json.loads(Path(config_path).read_text())
    notion_cfg = config["notion"]
    client = NotionClient(notion_cfg["api_key"])

    county_ids_path = Path(config_path).parent / "data" / "county_ids.json"
    county_ids: dict[str, str] = json.loads(county_ids_path.read_text())
    # Invert: notion_page_id → fips
    page_id_to_fips = {v: k for k, v in county_ids.items()}

    # ── Pull all STRIKES ──────────────────────────────────────────────────
    logger.info("Fetching all STRIKES records from Notion...")
    all_strikes = client.query_all(notion_cfg["databases"]["strikes"])
    logger.info(f"Found {len(all_strikes)} strike records")

    # Deduplicate by Cornell ID — concurrent ingest runs left some archived pages
    # appearing in paginated results. Keep only the first page per Cornell ID.
    seen_cornell_ids: set[int] = set()
    deduped_strikes = []
    for strike in all_strikes:
        cid = strike.get("properties", {}).get("Cornell ID", {}).get("number")
        if cid is not None:
            cid_int = int(cid)
            if cid_int in seen_cornell_ids:
                continue
            seen_cornell_ids.add(cid_int)
        deduped_strikes.append(strike)

    logger.info(f"After Cornell ID dedup: {len(deduped_strikes)} unique records "
                f"(removed {len(all_strikes) - len(deduped_strikes)} duplicates)")
    all_strikes = deduped_strikes

    # ── Aggregate by county FIPS ──────────────────────────────────────────
    # county_fips → {count, total_workers, has_worker_data, most_recent_year}
    county_agg: dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "total_workers": 0,
        "has_worker_data": False,
        "most_recent_year": None,
    })

    unmatched = 0
    for strike in all_strikes:
        county_relations = get_prop(strike, "Primary County", "relation") or []
        if not county_relations:
            unmatched += 1
            continue

        for county_page_id in county_relations:
            fips = page_id_to_fips.get(county_page_id)
            if not fips:
                continue

            agg = county_agg[fips]
            agg["count"] += 1

            workers = get_prop(strike, "Workers Involved", "number")
            if workers is not None:
                agg["has_worker_data"] = True
                agg["total_workers"] += int(workers)

            start_date = get_prop(strike, "Start Date", "date")
            if start_date:
                try:
                    yr = int(start_date[:4])
                    if agg["most_recent_year"] is None or yr > agg["most_recent_year"]:
                        agg["most_recent_year"] = yr
                except (ValueError, IndexError):
                    pass

    logger.info(
        f"Aggregated strikes to {len(county_agg)} counties "
        f"({unmatched} records with no county match)"
    )

    # ── Compute scores ────────────────────────────────────────────────────
    strike_scores: dict[str, float] = {}
    for fips, agg in county_agg.items():
        freq = score_frequency(agg["count"])
        scale = score_scale(agg["total_workers"], agg["has_worker_data"])
        recency = score_recency(agg["most_recent_year"])
        strike_scores[fips] = compute_strike_score(freq, scale, recency)

    nonzero = len(strike_scores)
    total_counties = len(county_ids)
    logger.info(
        f"Strike scores computed: {nonzero} counties with non-zero scores "
        f"({nonzero/total_counties*100:.1f}% of {total_counties} total counties)"
    )

    if dry_run:
        top = sorted(strike_scores.items(), key=lambda x: -x[1])[:20]
        print(f"\nTop 20 counties by strike_activity_score:")
        for fips, score in top:
            agg = county_agg[fips]
            print(
                f"  {fips}  score={score:.1f}  "
                f"strikes={agg['count']}  workers={agg['total_workers']}  "
                f"recent={agg['most_recent_year']}"
            )
        print(f"\nCoverage: {nonzero}/{total_counties} counties have non-zero score")
        return

    # ── Merge into county_scores.json ─────────────────────────────────────
    scores_path = Path(config_path).parent / "data" / "county_scores.json"
    if not scores_path.exists():
        logger.error("county_scores.json not found — run Task 9 first")
        return

    scores = json.loads(scores_path.read_text())
    updated = 0
    for record in scores:
        fips = record.get("fips", "")
        record["strike_activity_score"] = strike_scores.get(fips, 0.0)
        if record["strike_activity_score"] > 0:
            updated += 1

    scores_path.write_text(json.dumps(scores, indent=2))
    logger.info(
        f"Updated county_scores.json: {updated} counties with non-zero strike scores, "
        f"{len(scores) - updated} counties with score=0"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../config.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print top 20 strike counties; do not write county_scores.json")
    args = parser.parse_args()
    run(args.config, args.dry_run)
