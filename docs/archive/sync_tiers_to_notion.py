"""
Push pre-computed scores from county_scores.json to Notion — no re-scoring.

Reads county_scores.json (already computed by task9 + enrich_msa locally) and
PATCHes each Notion county page with the recalibrated scores and priority tier.
Skips the per-county employment/union/strike queries that task9 requires,
making this safe to run even if the employment database is 404ing.

Usage:
    python sync_tiers_to_notion.py [--config ../config.json] [--dry-run]
    python sync_tiers_to_notion.py --only-tier   # only patch Priority Tier (fastest)
"""

import json, logging, sys, time, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from notion_client import NotionClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / "logs" / "sync_tiers.log"),
    ],
)
logger = logging.getLogger(__name__)


def number_prop(v):
    return {"number": round(float(v), 2) if v is not None else None}

def select_prop(v):
    return {"select": {"name": str(v)} if v else None}


def run(config_path: str = "../config.json", only_tier: bool = False, dry_run: bool = False):
    cfg = json.loads(Path(config_path).read_text())
    notion_cfg = cfg["notion"]
    client = NotionClient(notion_cfg["api_key"])
    counties_db = notion_cfg["databases"]["counties"]

    scores = json.loads(Path("../data/county_scores.json").read_text())
    logger.info(f"Loaded {len(scores)} counties from county_scores.json")

    # Build fips → Notion page_id by querying the counties database
    logger.info("Fetching county page IDs from Notion...")
    notion_pages = client.query_all(counties_db)
    fips_to_page: dict[str, str] = {}
    for page in notion_pages:
        props = page.get("properties", {})
        fips_rich = props.get("FIPS", {}).get("rich_text", [])
        fips = fips_rich[0]["text"]["content"].strip().zfill(5) if fips_rich else ""
        if fips:
            fips_to_page[fips] = page["id"]
    logger.info(f"Mapped {len(fips_to_page)} FIPS codes to Notion pages")

    updated = skipped = errors = 0

    for i, c in enumerate(scores, 1):
        fips = str(c.get("fips", "")).zfill(5)
        page_id = fips_to_page.get(fips)
        if not page_id:
            skipped += 1
            continue

        tier = c.get("priority_tier", "C: Lower Priority")
        intervention = c.get("intervention_type", "")

        if only_tier:
            props = {
                "Priority Tier": select_prop(tier),
            }
        else:
            props = {
                "Organizing Opportunity Score": number_prop(c.get("organizing_opportunity_score")),
                "Electoral Geography Score":    number_prop(c.get("electoral_score")),
                "Presidential Score":           number_prop(c.get("presidential_score")),
                "Statewide Score":              number_prop(c.get("statewide_score")),
                "Congressional Score":          number_prop(c.get("congressional_score")),
                "Organizing Potential Score":   number_prop(c.get("organizing_score")),
                "Sectoral Value Score":         number_prop(c.get("sectoral_score")),
                "Infrastructure Score":         number_prop(c.get("infra_score")),
                "Organized Scale Score":        number_prop(c.get("organized_scale_score")),
                "Union Culture Score":          number_prop(c.get("union_culture_score")),
                "Strategic Terrain Score":      number_prop(c.get("terrain_score")),
                "Priority Tier":               select_prop(tier),
                "Intervention Type":           select_prop(intervention),
            }

        if dry_run:
            logger.info(f"DRY RUN {fips}: {tier}")
            updated += 1
            continue

        try:
            client.update_page(page_id, props)
            updated += 1
            if updated % 100 == 0:
                logger.info(f"Updated {updated}/{len(scores)} counties")
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"Failed {fips}: {e}")
            errors += 1

    from collections import Counter
    tier_counts = Counter(c.get("priority_tier", "?")[0] for c in scores)
    logger.info(
        f"Done. {updated} updated, {skipped} skipped (no page_id), {errors} errors"
    )
    logger.info(f"Tiers in local data: A={tier_counts['A']} B={tier_counts['B']} C={tier_counts['C']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="../config.json")
    p.add_argument("--only-tier", action="store_true", help="Only patch Priority Tier field")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    run(args.config, args.only_tier, args.dry_run)
