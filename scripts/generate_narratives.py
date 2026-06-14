"""
Terrain v2.0 — County strategic narrative generator.

Generates 2-3 sentence strategic assessments for each county using Claude Haiku.
Reads data/county_scores.json and writes narratives back in place.

Usage:
    python scripts/generate_narratives.py --test   # 5 counties, prints only
    python scripts/generate_narratives.py --full   # all tier1-3 counties, writes file

Safe to re-run: skips counties that already have a narrative field.
"""

import anthropic
import argparse
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_PATH = ROOT / "data" / "county_scores.json"

# Load .env — check worktree root, then main repo root
_env_path = ROOT / ".env"
if not _env_path.exists():
    _env_path = Path("/Users/samkaplanpettus/labor_organizing_model/.env")
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

client = anthropic.Anthropic()

TIER_DESCS = {
    "tier1_capital": "High capital leverage + hostile incumbent",
    "tier1_community": "High community leverage + hostile incumbent",
    "tier1_capital_community": "High capital + community leverage + hostile incumbent",
    "tier2_activate_capital": "Capital leverage + aligned incumbent",
    "tier2_activate_community": "Community leverage + aligned incumbent",
    "tier2_activate_capital_community": "Capital + community leverage + aligned incumbent",
    "tier2_unknown_capital": "High capital leverage, incumbent alignment unclear",
    "tier2_unknown_community": "High community leverage, incumbent alignment unclear",
    "tier2_unknown_capital_community": "High capital + community leverage, incumbent alignment unclear",
    "tier2_build_capital": "High capital leverage, safe state — build electoral conditions",
    "tier2_build_community": "High community leverage, safe state — build electoral conditions",
    "tier2_build_capital_community": "High capital + community leverage, safe state",
    "tier3_electoral": "Decisive electoral terrain — build organizing base",
}


def generate_narrative(county: dict, tier_desc: str) -> str:
    margin = county.get("margin_2024") or 0
    margin_str = f"{'D+' if margin >= 0 else 'R+'}{abs(margin):.1f}"
    prompt = (
        f"Write a 2-3 sentence strategic assessment for a labor organizer. "
        f"Be concrete, direct, under 60 words. No jargon. "
        f"County: {county['county_name']}, {county['state']}. "
        f"Population: {county.get('population') or 0:,}. "
        f"Tier: {tier_desc}. "
        f"Capital Leverage: {(county.get('sls_capital') or 0):.1f}/100. "
        f"Community Leverage: {(county.get('sls_community') or 0):.1f}/100. "
        f"Electoral P1: {(county.get('p1_presidential') or 0):.1f}/100. "
        f"Federal P2 alignment: {int((county.get('federal_p2') or 0) * 100)}%. "
        f"2024 margin: {margin_str}. "
        f"Explain what makes this county strategically significant, "
        f"what leverage exists, and what organizing here accomplishes."
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def tier4_narrative(county: dict) -> str:
    return (
        f"{county.get('county_name', 'This county')} falls below current strategic "
        f"thresholds on both leverage dimensions and electoral geography."
    )


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--test", action="store_true",
                      help="Process 5 counties, print narratives, do not write file")
    mode.add_argument("--full", action="store_true",
                      help="Process all eligible counties and write to county_scores.json")
    args = parser.parse_args()

    with open(DATA_PATH) as f:
        data = json.load(f)

    counties = data["counties"]

    # Separate tiers
    actionable = [c for c in counties
                  if (c.get("quadrant_national") or "").startswith(("tier1", "tier2", "tier3"))
                  and not c.get("narrative")]
    tier4 = [c for c in counties
             if (c.get("quadrant_national") or "tier4") == "tier4"
             and not c.get("narrative")]

    print(f"Counties needing narratives: {len(actionable)} actionable + {len(tier4)} tier4")

    if args.test:
        # Pick 5 representative counties across tiers
        sample = []
        for tier_prefix in ("tier1_", "tier2_activate", "tier2_build", "tier2_unknown", "tier3_"):
            for c in actionable:
                if (c.get("quadrant_national") or "").startswith(tier_prefix):
                    sample.append(c)
                    break
        sample = sample[:5]
        print(f"\nGenerating {len(sample)} test narratives...\n")
        for county in sample:
            qn = county.get("quadrant_national", "tier4")
            tier_desc = TIER_DESCS.get(qn, qn)
            narrative = generate_narrative(county, tier_desc)
            print(f"=== {county['county_name']}, {county['state']} ({county['fips']}) ===")
            print(f"Quadrant: {qn}")
            print(f"Narrative: {narrative}")
            print()
        print("-- Test complete. Run with --full after Sam approves. --")
        return

    # Full run
    total = len(actionable) + len(tier4)
    processed = 0

    # Tier4 — template-based (no API call)
    for county in tier4:
        county["narrative"] = tier4_narrative(county)
        processed += 1

    # Actionable — API calls
    errors = []
    for county in actionable:
        qn = county.get("quadrant_national", "tier4")
        tier_desc = TIER_DESCS.get(qn, qn)
        try:
            county["narrative"] = generate_narrative(county, tier_desc)
            processed += 1
            if processed % 50 == 0:
                print(f"  {processed}/{total} narratives generated...")
            time.sleep(0.3)  # gentle rate limit
        except Exception as e:
            errors.append({"fips": county.get("fips"), "error": str(e)})
            county["narrative"] = None

    print(f"\nGenerated {processed} narratives ({len(errors)} errors)")

    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote updated data to {DATA_PATH}")

    if errors:
        print("Errors:")
        for e in errors[:10]:
            print(f"  {e['fips']}: {e['error']}")


if __name__ == "__main__":
    main()
