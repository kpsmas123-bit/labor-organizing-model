"""
Build-time enrichment: generate MSA labor summaries and county score explanations.

For each Metropolitan/Micropolitan Statistical Area:
  1. Fetches recent news headlines from NewsAPI.org
  2. Calls claude-haiku-4-5 (with prompt caching on the system prompt) to produce:
     - A 2-3 sentence MSA labor politics summary based on news + strike/union data
     - A plain-language explanation for each county's terrain score

Output: data/msa_summaries.json
  {
    "msa_summaries": { "<msa_code>": { "summary": "...", "fetched_at": "..." } },
    "county_explanations": { "<fips>": "..." }
  }

Usage:
    NEWSAPI_KEY=<key> ANTHROPIC_API_KEY=<key> python enrich_summaries.py
    python enrich_summaries.py --scores ../data/county_scores.json --out ../data/msa_summaries.json
    python enrich_summaries.py --top-msas-only   # only process MSAs with ≥1 A-tier county
    python enrich_summaries.py --dry-run          # print prompts, skip API calls
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / "logs" / "enrich_summaries.log"),
    ],
)
logger = logging.getLogger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2/everything"

SYSTEM_PROMPT = """\
You are a labor organizing strategist writing concise intelligence briefs for field organizers.
Your job is to synthesize local news and quantitative data into actionable insights.

Guidelines:
- Be specific and concrete. Name industries, unions, employers, or campaigns when present.
- Treat the terrain score as an index of organizing opportunity (higher = more favorable conditions).
- Scores are driven by: electoral climate (35%), organizing conditions (30%), sectoral density (25%), infrastructure (10%).
- Write for a smart non-expert reader — no jargon without explanation.
- Keep MSA summaries to 2-3 sentences. Keep county explanations to 1-2 sentences.
- If news is sparse, rely on the quantitative profile to explain conditions.
"""

COUNTY_SCORE_FIELDS = [
    ("terrain_score",           "Overall terrain score (0-100)"),
    ("electoral_score",         "Electoral climate (0-100)"),
    ("organizing_score",        "Organizing conditions (0-100)"),
    ("sectoral_score",          "Sectoral density (0-100)"),
    ("infra_score",             "Infrastructure (0-100)"),
    ("priority_tier",           "Priority tier (A/B/C)"),
    ("population",              "Population"),
    ("rural_urban",             "Rural/urban classification"),
    ("swing_state",             "Swing state"),
    ("margin_2024",             "2024 presidential margin (positive = Dem)"),
    ("union_culture_score",     "Union culture score (0-100)"),
    ("intervention_type",       "Recommended intervention type"),
]


def fetch_news(msa_name: str, api_key: str, days_back: int = 30) -> list[str]:
    """Return up to 5 headline strings for the MSA. Returns [] on failure."""
    if not api_key:
        return []

    # Strip state suffix (everything after the last comma) for cleaner queries
    city = msa_name.split(",")[0].strip()
    query = f'("{city}") AND (union OR strike OR labor OR workers OR organizing)'

    from datetime import timedelta
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    try:
        resp = requests.get(
            NEWSAPI_BASE,
            params={
                "q": query,
                "from": from_date,
                "sortBy": "relevancy",
                "pageSize": 5,
                "language": "en",
                "apiKey": api_key,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        headlines = [
            f"{a['title']} ({a['source']['name']})"
            for a in data.get("articles", [])
            if a.get("title")
        ]
        return headlines[:5]
    except Exception as e:
        logger.warning(f"News fetch failed for '{msa_name}': {e}")
        return []


def county_profile_text(county: dict) -> str:
    lines = [f"County: {county['county_name']}, {county['state']}"]
    for field, label in COUNTY_SCORE_FIELDS:
        val = county.get(field)
        if val is not None:
            lines.append(f"  {label}: {val}")
    return "\n".join(lines)


def build_user_message(msa_name: str, msa_type: str, counties: list[dict], headlines: list[str]) -> str:
    parts = [f"MSA: {msa_name} ({msa_type})"]

    if headlines:
        parts.append("\nRecent labor news headlines:")
        for h in headlines:
            parts.append(f"  - {h}")
    else:
        parts.append("\n(No recent labor news found — rely on quantitative data.)")

    parts.append(f"\nCounties in this MSA ({len(counties)} total):")
    for c in sorted(counties, key=lambda x: -x.get("terrain_score", 0)):
        parts.append(county_profile_text(c))

    parts.append(
        "\n---\n"
        "Please write:\n"
        "1. A 2-3 sentence labor politics summary for this MSA as a whole.\n"
        "2. For each county listed, a 1-2 sentence plain-language explanation of "
        "why it receives its terrain score. Start each county explanation with the county name.\n"
        "Format: first the MSA summary paragraph, then a numbered list of county explanations "
        "prefixed with the county name."
    )

    return "\n".join(parts)


def parse_response(text: str, counties: list[dict]) -> tuple[str, dict[str, str]]:
    """Split Claude's response into MSA summary and per-county explanations."""
    lines = text.strip().split("\n")

    # MSA summary: everything before the first county name appears
    county_names_lower = {c["county_name"].lower() for c in counties}
    summary_lines = []
    remainder_start = 0

    for i, line in enumerate(lines):
        if any(name in line.lower() for name in county_names_lower):
            remainder_start = i
            break
        summary_lines.append(line)
    else:
        remainder_start = len(lines)

    msa_summary = " ".join(l.strip() for l in summary_lines if l.strip())

    # County explanations: match lines that start with or contain a county name
    county_map: dict[str, str] = {}
    current_fips = None
    current_text = []

    def flush():
        if current_fips and current_text:
            county_map[current_fips] = " ".join(current_text).strip()

    fips_by_name = {c["county_name"].lower(): c["fips"] for c in counties}

    for line in lines[remainder_start:]:
        stripped = line.strip().lstrip("0123456789.-) ").strip()
        matched_fips = None
        for name, fips in fips_by_name.items():
            if name in stripped.lower():
                matched_fips = fips
                break
        if matched_fips:
            flush()
            current_fips = matched_fips
            current_text = [stripped]
        elif current_fips and stripped:
            current_text.append(stripped)
    flush()

    return msa_summary, county_map


def run(
    scores_path: str = "../data/county_scores.json",
    out_path: str = "../data/msa_summaries.json",
    top_msas_only: bool = False,
    dry_run: bool = False,
):
    news_key = os.environ.get("NEWSAPI_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not anthropic_key and not dry_run:
        logger.error("ANTHROPIC_API_KEY not set — aborting")
        sys.exit(1)
    if not news_key:
        logger.warning("NEWSAPI_KEY not set — skipping news fetch, using data only")

    client = anthropic.Anthropic(api_key=anthropic_key) if not dry_run else None

    scores = json.loads(Path(scores_path).read_text())

    # Group counties by MSA
    msa_groups: dict[str, list[dict]] = defaultdict(list)
    for c in scores:
        msa_name = c.get("msa_name") or "Non-Metro"
        if msa_name != "Non-Metro":
            msa_groups[msa_name].append(c)

    logger.info(f"Loaded {len(scores)} counties across {len(msa_groups)} real MSAs")

    # Load existing output to allow resume without re-processing
    out_file = Path(out_path)
    existing: dict = {}
    if out_file.exists():
        existing = json.loads(out_file.read_text())
        logger.info(
            f"Resuming: {len(existing.get('msa_summaries', {}))} MSAs already processed"
        )

    msa_summaries: dict = existing.get("msa_summaries", {})
    county_explanations: dict = existing.get("county_explanations", {})

    # Build ordered work list: A-heavy MSAs first
    def msa_priority(item):
        name, counties = item
        a_count = sum(1 for c in counties if c.get("priority_tier", "").startswith("A"))
        b_count = sum(1 for c in counties if c.get("priority_tier", "").startswith("B"))
        return -(a_count * 10 + b_count)

    work_list = sorted(msa_groups.items(), key=msa_priority)

    if top_msas_only:
        work_list = [(n, cs) for n, cs in work_list if any(
            c.get("priority_tier", "").startswith("A") for c in cs
        )]
        logger.info(f"--top-msas-only: processing {len(work_list)} MSAs with ≥1 A-tier county")

    total = len(work_list)
    processed = skipped = errors = 0

    for i, (msa_name, counties) in enumerate(work_list, 1):
        msa_code = counties[0].get("msa_code") or msa_name

        # Skip if already done
        if msa_code in msa_summaries and all(
            c["fips"] in county_explanations for c in counties
        ):
            skipped += 1
            continue

        logger.info(f"[{i}/{total}] {msa_name} ({len(counties)} counties)")

        headlines = fetch_news(msa_name, news_key) if news_key else []
        if headlines:
            logger.info(f"  {len(headlines)} headlines fetched")

        user_msg = build_user_message(
            msa_name,
            counties[0].get("msa_type", "Metro"),
            counties,
            headlines,
        )

        if dry_run:
            logger.info(f"  [DRY RUN] system prompt ({len(SYSTEM_PROMPT)} chars) + user ({len(user_msg)} chars)")
            processed += 1
            continue

        try:
            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_msg}],
            )

            text = response.content[0].text
            msa_summary, county_map = parse_response(text, counties)

            msa_summaries[msa_code] = {
                "msa_name": msa_name,
                "msa_type": counties[0].get("msa_type", "Metro"),
                "summary": msa_summary,
                "news_headlines": headlines,
                "county_count": len(counties),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "cache_read": getattr(response.usage, "cache_read_input_tokens", 0),
                    "cache_write": getattr(response.usage, "cache_creation_input_tokens", 0),
                },
            }

            county_explanations.update(county_map)
            processed += 1

            # Write checkpoint every 10 MSAs
            if processed % 10 == 0:
                out_file.write_text(
                    json.dumps(
                        {"msa_summaries": msa_summaries, "county_explanations": county_explanations},
                        indent=2,
                    )
                )
                logger.info(f"  Checkpoint saved ({processed} processed so far)")

            time.sleep(0.3)  # polite rate limiting

        except Exception as e:
            logger.error(f"  Claude API error for '{msa_name}': {e}")
            errors += 1
            time.sleep(2)

    # Final write
    out_file.write_text(
        json.dumps(
            {"msa_summaries": msa_summaries, "county_explanations": county_explanations},
            indent=2,
        )
    )

    logger.info(
        f"Done. {processed} processed, {skipped} skipped (already done), {errors} errors."
    )
    logger.info(f"Output: {out_file} — {len(msa_summaries)} MSA summaries, {len(county_explanations)} county explanations")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scores", default="../data/county_scores.json")
    p.add_argument("--out", default="../data/msa_summaries.json")
    p.add_argument("--top-msas-only", action="store_true", help="Only process MSAs with ≥1 A-tier county")
    p.add_argument("--dry-run", action="store_true", help="Print prompts, skip API calls")
    args = p.parse_args()
    run(args.scores, args.out, args.top_msas_only, args.dry_run)
