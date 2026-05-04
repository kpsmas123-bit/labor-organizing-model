"""
Generate plain-language labor intelligence summaries for each MSA.

Reads county_scores.json, groups counties by msa_name, aggregates scores,
then calls Claude to write a 2-3 sentence brief for each MSA explaining what
makes it score the way it does and what kind of organizing intervention it calls for.

Output: data/msa_summaries.json (keyed by MSA name, read by the dashboard gallery)

API key: add "anthropic_api_key": "sk-ant-..." to config.json

Usage:
    python enrich_msa_summaries.py
    python enrich_msa_summaries.py --top-only          # OOS >= 70 only
    python enrich_msa_summaries.py --limit 10          # first 10 MSAs (test run)
    python enrich_msa_summaries.py --output /tmp/out.json
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# ── Locate files relative to this script ──────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT   = SCRIPT_DIR.parent

def _find(candidates: list[Path]) -> Path:
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Could not find file. Tried:\n" + "\n".join(f"  {p}" for p in candidates)
    )

CONFIG_PATH  = _find([REPO_ROOT / "config.json"])
SCORES_PATH  = _find([
    REPO_ROOT / "data"   / "county_scores.json",   # actual location
    REPO_ROOT / "output" / "county_scores.json",   # spec location (fallback)
])
DEFAULT_OUT  = REPO_ROOT / "data" / "msa_summaries.json"

# ── Intervention type descriptions ────────────────────────────────────────────
INT_DEFS = {
    "A": ("Type A: Organize the Unorganized",
          "Few or no unions here. Build from scratch — find the leaders, run the drive, build the structure."),
    "B": ("Type B: Politically Activate Existing Unions",
          "Unions exist but aren't punching their weight electorally. Mobilize members into durable political power."),
    "C": ("Type C: Partner with Activated Unions",
          "Strong, politically engaged unions. Coordinate across locals for maximum voter contact and issue leverage."),
}

MODEL = "claude-sonnet-4-6"


def load_config() -> dict:
    import os
    cfg = json.loads(CONFIG_PATH.read_text())
    key = cfg.get("anthropic_api_key", "")
    if not key or key.startswith("YOUR_"):
        # Fall back to environment variable (works in Claude Code runtime)
        env_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if env_key:
            cfg["anthropic_api_key"] = env_key
        else:
            # Try instantiating without explicit key — SDK may find credentials itself
            cfg["anthropic_api_key"] = None
    return cfg


def group_by_msa(scores: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for c in scores:
        name = c.get("msa_name")
        if not name or name == "Non-Metro":
            continue
        groups.setdefault(name, []).append(c)
    return groups


def aggregate(counties: list[dict]) -> dict:
    n = len(counties)

    def avg(field: str):
        vals = [c[field] for c in counties if c.get(field) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    total_pop = sum(c.get("population") or 0 for c in counties)

    # Dominant intervention type by county count
    type_counts = Counter(
        (c.get("intervention_type") or "")[:6].strip()   # "Type A", "Type B", "Type C"
        for c in counties
    )
    dominant_raw = type_counts.most_common(1)[0][0] if type_counts else ""
    dominant_letter = dominant_raw[-1] if dominant_raw else "A"   # "A", "B", or "C"

    # State list
    states = sorted({c.get("state", "") for c in counties if c.get("state")})

    return {
        "oos_score":           avg("organizing_opportunity_score"),
        "terrain_score":       avg("terrain_score"),
        "organizing_score":    avg("organizing_score"),
        "sectoral_score":      avg("sectoral_score"),
        "infra_score":         avg("infra_score"),
        "electoral_score":     avg("electoral_score"),
        "presidential_score":  avg("presidential_score"),
        "statewide_score":     avg("statewide_score"),
        "congressional_score": avg("congressional_score"),
        "union_culture_score": avg("union_culture_score"),
        "organized_scale_score": avg("organized_scale_score"),
        "total_population":    total_pop or None,
        "county_count":        n,
        "dominant_type":       dominant_letter,
        "states":              ", ".join(states),
        "priority_tiers":      Counter(
            (c.get("priority_tier") or "C")[0] for c in counties
        ),
        "rural_urban_mix":     Counter(c.get("rural_urban", "") for c in counties),
    }


def build_prompt(msa_name: str, agg: dict) -> str:
    int_letter = agg["dominant_type"]
    int_name, int_desc = INT_DEFS.get(int_letter, INT_DEFS["A"])

    def fmt(v, suffix=""):
        return f"{v}{suffix}" if v is not None else "N/A"

    tiers = agg["priority_tiers"]
    tier_str = f"A={tiers.get('A',0)}, B={tiers.get('B',0)}, C={tiers.get('C',0)} counties"

    electoral_note = ""
    for label, field in [
        ("presidential", "presidential_score"),
        ("statewide", "statewide_score"),
        ("congressional", "congressional_score"),
    ]:
        v = agg.get(field)
        if v is not None and v >= 70:
            electoral_note += f"  {label.capitalize()} score: {v}/100 (HIGH — electoral leverage is real)\n"
    if not electoral_note:
        electoral_note = "  No electoral sub-score exceeds 70 — not a high-leverage swing area.\n"

    pop_str = f"{agg['total_population']:,}" if agg["total_population"] else "unknown"

    return f"""You are writing a labor organizing intelligence brief for field organizers. Be specific and concrete. No jargon without explanation. Write for someone who has never heard of this place.

MSA: {msa_name}
States covered: {agg['states']}
Counties in MSA: {agg['county_count']} ({tier_str})
Total population: {pop_str}

SCORES (all 0–100 unless noted):
  Organizing Opportunity Score (OOS): {fmt(agg['oos_score'])}
  Strategic Terrain Score: {fmt(agg['terrain_score'])}
  Organizing potential (unorganized workforce): {fmt(agg['organizing_score'])}
  Sectoral value (leverage of dominant industries): {fmt(agg['sectoral_score'])}
  Infrastructure (existing union presence/density): {fmt(agg['infra_score'])}
  Union culture score: {fmt(agg['union_culture_score'])}
  Organized scale score: {fmt(agg['organized_scale_score'])}

ELECTORAL RELEVANCE:
{electoral_note}
RECOMMENDED INTERVENTION: {int_name}
  → {int_desc}

Write exactly 2-3 sentences that:
1. Explain in plain English what makes this MSA score the way it does — what the numbers mean about the actual workers and industries here
2. Name the dominant industries implied by the sectoral value score (high = hospitals, schools, ports, utilities; low = retail, finance, tech) and why they matter strategically
3. If any electoral score exceeds 70, connect organizing capacity to electoral impact; if not, skip electoral framing
4. State clearly what the recommended intervention means in practice for an organizer walking in the door

Return only the 2-3 sentence brief. No headers, no bullet points, no preamble."""


def call_claude(client, prompt: str):
    """Returns (text, input_tokens, output_tokens)."""
    import anthropic as _anth
    msg = client.messages.create(
        model=MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip() if msg.content else ""
    return text, msg.usage.input_tokens, msg.usage.output_tokens


def check_dashboard_wiring() -> bool:
    """Check if dashboard already reads msa_summaries.json and what field it expects."""
    dash = REPO_ROOT / "output" / "labor_organizing_national_dashboard.html"
    if not dash.exists():
        return False
    html = dash.read_text()
    if "msa_summaries.json" in html and "msa_name" in html and ".summary" in html:
        print("[Dashboard] ✓ Already wired: reads msa_summaries.json, indexes by msa_name, reads .summary field")
        return True
    return False


def wire_dashboard(out_path: Path):
    """Add msa_summaries loading + gallery card display if not already present."""
    dash = REPO_ROOT / "output" / "labor_organizing_national_dashboard.html"
    if not dash.exists():
        print("[Dashboard] Not found — skipping wiring")
        return

    html = dash.read_text()

    # Check if already wired
    if "msa_summaries.json" in html:
        print("[Dashboard] Already reads msa_summaries.json — no changes needed")
        return

    # Inject fetch into loadData()
    load_inject = """
  // Load build-time MSA summaries (generated by enrich_msa_summaries.py)
  try {
    const sr = await fetch("../data/msa_summaries.json");
    if (sr.ok) {
      const sd = await sr.json();
      for (const [, v] of Object.entries(sd.msa_summaries || {})) {
        if (v.msa_name && v.summary) gl_msaSummaries[v.msa_name] = v;
      }
      gl_countyExplanations = sd.county_explanations || {};
      console.log(`[Data] ${Object.keys(gl_msaSummaries).length} MSA summaries loaded`);
    }
  } catch (_) { /* not yet generated */ }"""

    # Inject before closing brace of loadData if not present
    if "gl_msaSummaries" not in html:
        # Add global vars
        html = html.replace(
            "let allCounties = [];",
            "let allCounties = [];\nlet gl_msaSummaries = {};\nlet gl_countyExplanations = {};",
        )
        # Inject fetch at end of loadData
        html = html.replace(
            'setStatus(`Loaded ${allCounties.length} scored counties`);',
            f'setStatus(`Loaded ${{allCounties.length}} scored counties`);{load_inject}',
        )

    # Inject summary display into gallery card if glBuildCard exists
    if "glBuildCard" in html and "gl_msaSummaries" in html and "msaSummaryData" not in html:
        card_inject = """
  const msaSummaryData = gl_msaSummaries[msa.name];
  let newsHTML;
  if (msaSummaryData && msaSummaryData.summary) {
    newsHTML = `<p class="gl-news-body gl-news-live">${msaSummaryData.summary}</p>`;
  } else {
    newsHTML = `<p class="gl-news-body">Run enrich_msa_summaries.py to generate summaries.</p>`;
  }"""
        html = html.replace(
            "const newsHTML = isTop",
            f"{card_inject}\n  const _newsHTMLOld = isTop",
        )

    dash.write_text(html)
    print("[Dashboard] ✓ Wired msa_summaries loading and gallery card display")


def run(
    top_only=False,
    limit=None,
    output_path=DEFAULT_OUT,
    dry_run=False,
):
    cfg = load_config()

    try:
        import anthropic
    except ImportError:
        print("[ERROR] 'anthropic' package not installed. Run: pip3 install anthropic")
        sys.exit(1)

    api_key = cfg.get("anthropic_api_key")
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    print(f"[Config] Reading scores from: {SCORES_PATH}")
    scores = json.loads(SCORES_PATH.read_text())
    print(f"[Config] {len(scores)} counties loaded")

    msa_groups = group_by_msa(scores)
    print(f"[Config] {len(msa_groups)} MSAs found (excluding Non-Metro)")

    # Check dashboard wiring
    already_wired = check_dashboard_wiring()
    if not already_wired:
        wire_dashboard(output_path)

    # Build work list
    work = list(msa_groups.items())

    if top_only:
        work = [
            (name, counties) for name, counties in work
            if any((c.get("organizing_opportunity_score") or 0) >= 70 for c in counties)
        ]
        print(f"[Filter] --top-only: {len(work)} MSAs with OOS ≥ 70")

    # Sort: highest avg OOS first
    work.sort(
        key=lambda x: -(sum(c.get("organizing_opportunity_score") or 0 for c in x[1]) / len(x[1]))
    )

    if limit:
        work = work[:limit]
        print(f"[Filter] --limit {limit}: processing {len(work)} MSAs")

    # Load existing output to allow resume
    existing: dict = {}
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text())
        except Exception:
            existing = {}
    msa_summaries: dict = existing.get("msa_summaries", {})
    county_explanations: dict = existing.get("county_explanations", {})

    total_input_tokens = total_output_tokens = 0
    processed = failed = skipped = 0

    for i, (msa_name, counties) in enumerate(work, 1):
        # Resume: skip if already done
        if msa_name in msa_summaries and msa_summaries[msa_name].get("summary"):
            skipped += 1
            print(f"[{i}/{len(work)}] {msa_name} — already done, skipping")
            continue

        agg = aggregate(counties)
        prompt = build_prompt(msa_name, agg)

        if dry_run:
            print(f"[{i}/{len(work)}] {msa_name} — DRY RUN ({len(prompt)} chars prompt)")
            processed += 1
            continue

        try:
            summary, inp, out = call_claude(client, prompt)
            total_input_tokens  += inp
            total_output_tokens += out

            msa_summaries[msa_name] = {
                "msa_name":         msa_name,
                "summary":          summary,
                "oos_score":        agg["oos_score"],
                "terrain_score":    agg["terrain_score"],
                "intervention_type": INT_DEFS.get(agg["dominant_type"], INT_DEFS["A"])[0],
                "county_count":     agg["county_count"],
                "states":           agg["states"],
                "generated_at":     datetime.now(timezone.utc).isoformat(),
            }
            processed += 1
            print(f"[{i}/{len(work)}] {msa_name} ✓  ({inp}+{out} tokens)")

            # Checkpoint every 25
            if processed % 25 == 0:
                output_path.write_text(
                    json.dumps({"msa_summaries": msa_summaries, "county_explanations": county_explanations}, indent=2)
                )

        except Exception as e:
            print(f"[{i}/{len(work)}] {msa_name} ✗  {e}")
            failed += 1

    # Final write
    output_path.write_text(
        json.dumps({"msa_summaries": msa_summaries, "county_explanations": county_explanations}, indent=2)
    )

    est_cost = (total_input_tokens / 1_000_000 * 3.0) + (total_output_tokens / 1_000_000 * 15.0)
    print(
        f"\n{'='*60}\n"
        f"  Processed : {processed}\n"
        f"  Skipped   : {skipped} (already done)\n"
        f"  Failed    : {failed}\n"
        f"  Output    : {output_path}\n"
        f"  Tokens    : {total_input_tokens:,} in / {total_output_tokens:,} out\n"
        f"  Est. cost : ${est_cost:.3f}\n"
        f"{'='*60}"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--top-only", action="store_true", help="Only MSAs with OOS >= 70")
    p.add_argument("--limit",    type=int,  default=None, metavar="N", help="Process at most N MSAs")
    p.add_argument("--output",   type=Path, default=DEFAULT_OUT,       help="Output JSON path")
    p.add_argument("--dry-run",  action="store_true", help="Build prompts but don't call API")
    args = p.parse_args()
    run(args.top_only, args.limit, args.output, args.dry_run)
