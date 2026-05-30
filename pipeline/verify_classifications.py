"""
Monthly classifier verification — re-classifies a random sample of jobs via
Claude API and compares against the current rules classifier output.

Usage:
    python -m pipeline.verify_classifications                    # 30-job sample
    python -m pipeline.verify_classifications --sample 50        # larger sample
    python -m pipeline.verify_classifications --seed 42          # reproducible

Writes data/verification_report.json when disagreement is found.
Requires ANTHROPIC_API_KEY in .env or environment.
Estimated cost: ~$0.01–$0.05 per run (30 jobs × haiku rates).
"""
import argparse
import asyncio
import json
import os
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

from pipeline.classify_jobs_rules import enrich_job as rules_enrich
from pipeline.enrich_jobs import build_prompt, parse_response, validate_enrichment

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL = "claude-haiku-4-5-20251001"
CONCURRENCY = 5
AGREEMENT_THRESHOLD = 0.80   # flag field if agreement rate drops below this
VERIFY_FIELDS = [
    "experience_level", "job_function", "location_type",
    "employment_type", "professional_staff", "supervisory",
]
# Fields where we compare list membership rather than equality
LIST_COMPARE_FIELDS = ["credentials_required", "benefits_signals", "background_required"]

INPUT_PATH  = Path("data/classified_jobs.json")
REPORT_PATH = Path("data/verification_report.json")


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------
def sample_jobs(jobs: list, n: int = 30, seed: Optional[int] = None) -> list:
    """
    Sample n jobs from the dataset.
    50% drawn from experience_confidence=0.5 jobs (weakest classifications),
    50% drawn at random from the remainder.
    """
    rng = random.Random(seed)

    # First, apply rules to get current confidence scores
    enriched = [rules_enrich(j) for j in jobs]

    low_conf = [j for j in enriched if j.get("experience_confidence") == 0.5]
    others   = [j for j in enriched if j.get("experience_confidence") != 0.5]

    n_low   = min(n // 2, len(low_conf))
    n_other = min(n - n_low, len(others))

    sample  = rng.sample(low_conf, n_low) + rng.sample(others, n_other)
    rng.shuffle(sample)
    return sample[:n]


# ---------------------------------------------------------------------------
# API classification
# ---------------------------------------------------------------------------
async def classify_one(
    client: anthropic.AsyncAnthropic,
    sem: asyncio.Semaphore,
    job: dict,
    idx: int,
    total: int,
) -> Optional[dict]:
    """Call Claude API to re-classify one job; returns enrichment dict or None."""
    prompt = build_prompt(job)
    label = (job.get("title") or "")[:50]
    for attempt in range(2):
        try:
            async with sem:
                response = await client.messages.create(
                    model=MODEL,
                    max_tokens=256,
                    messages=[{"role": "user", "content": prompt}],
                )
            text = response.content[0].text
            data = parse_response(text)
            if data:
                data = validate_enrichment(data)
                print(f"  [{idx+1:>2}/{total}] {label!r}  OK")
                return data
            else:
                print(f"  [{idx+1:>2}/{total}] {label!r}  PARSE_ERROR (attempt {attempt+1})")
        except Exception as exc:
            print(f"  [{idx+1:>2}/{total}] {label!r}  ERROR: {exc} (attempt {attempt+1})")
    return None


async def run_api_batch(jobs: list, concurrency: int = CONCURRENCY) -> list:
    """Run API classification for all jobs; returns list of results (None on failure)."""
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not set. "
            "Add it to .env or export it as an environment variable."
        )
    client = anthropic.AsyncAnthropic(api_key=api_key)
    sem    = asyncio.Semaphore(concurrency)
    tasks  = [
        classify_one(client, sem, job, idx, len(jobs))
        for idx, job in enumerate(jobs)
    ]
    return await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# Comparison + analysis
# ---------------------------------------------------------------------------
def compare(rules_jobs: list, api_results: list) -> dict:
    """
    Compare rules-classifier output vs API output per field.
    Returns per-field stats dict.
    """
    all_fields = VERIFY_FIELDS + LIST_COMPARE_FIELDS
    stats = {
        f: {"agree": 0, "disagree": 0, "examples": []}
        for f in all_fields
    }
    for rules_job, api_out in zip(rules_jobs, api_results):
        if api_out is None:
            continue
        for field in VERIFY_FIELDS:
            r_val = rules_job.get(field)
            a_val = api_out.get(field)
            if r_val == a_val:
                stats[field]["agree"] += 1
            else:
                stats[field]["disagree"] += 1
                if len(stats[field]["examples"]) < 20:
                    stats[field]["examples"].append({
                        "job_id": rules_job.get("job_id"),
                        "title":  rules_job.get("title"),
                        "rules":  r_val,
                        "api":    a_val,
                    })
        # For list fields: compare as sets — agree if sets are equal
        for field in LIST_COMPARE_FIELDS:
            r_set = set(rules_job.get(field) or [])
            a_set = set(api_out.get(field) or [])
            if r_set == a_set:
                stats[field]["agree"] += 1
            else:
                stats[field]["disagree"] += 1
                if len(stats[field]["examples"]) < 20:
                    stats[field]["examples"].append({
                        "job_id":        rules_job.get("job_id"),
                        "title":         rules_job.get("title"),
                        "rules":         sorted(r_set),
                        "api":           sorted(a_set),
                        "api_only":      sorted(a_set - r_set),
                        "rules_only":    sorted(r_set - a_set),
                    })
    return stats


def agreement_rates(stats: dict) -> dict[str, float]:
    all_fields = VERIFY_FIELDS + LIST_COMPARE_FIELDS
    rates = {}
    for field in all_fields:
        s = stats.get(field, {"agree": 0, "disagree": 0})
        total = s["agree"] + s["disagree"]
        rates[field] = s["agree"] / total if total else 1.0
    return rates


# ---------------------------------------------------------------------------
# Amendment proposals
# ---------------------------------------------------------------------------
def propose_amendments(stats: dict, failing_fields: list) -> list:
    """
    Analyse disagreement patterns for each failing field and propose
    targeted rule amendments in classify_jobs_rules.py.
    """
    proposals = []

    for field in failing_fields:
        examples = stats[field]["examples"]

        # ── List fields: generate patterns from api_only items ─────────────
        if field in LIST_COMPARE_FIELDS:
            api_only_counts: dict[str, list[str]] = defaultdict(list)
            for ex in examples:
                for item in (ex.get("api_only") or []):
                    api_only_counts[item].append(ex.get("title") or "")
            for item, titles in sorted(api_only_counts.items(), key=lambda x: -len(x[1])):
                pattern_name = f"_BG_RE" if field == "background_required" else f"_CRED_RE" if field == "credentials_required" else f"_BEN_RE"
                code_snippet = (
                    f'# Add to {field} patterns in classify_jobs_rules.py:\n'
                    f'(re.compile(r\'\\b{re.escape(item)}\\b\', re.IGNORECASE), "{item}"),'
                )
                proposals.append({
                    "field":            field,
                    "transition":       f"rules missing → api found '{item}'",
                    "count":            len(titles),
                    "example_titles":   titles[:5],
                    "suggested_action": f"Add pattern for '{item}' to extract_{field}() in classify_jobs_rules.py",
                    "proposed_code":    code_snippet,
                })
            continue

        # Group by (rules_value → api_value) transition
        transitions: dict[str, list[str]] = defaultdict(list)
        for ex in examples:
            key = f"{ex['rules']} → {ex['api']}"
            transitions[key].append(ex["title"] or "")

        for transition, titles in sorted(transitions.items(), key=lambda x: -len(x[1])):
            r_val, a_val = (t.strip() for t in transition.split("→", 1))

            # ── experience_level advice ────────────────────────────────────
            if field == "experience_level":
                if r_val in ("experienced", "early-career") and a_val == "leadership":
                    action = (
                        f"Consider adding title keywords for these roles to "
                        f"_LEAD_STRONG_RE or _LEAD_MOD_RE in classify_jobs_rules.py"
                    )
                    code_snippet = (
                        f"# Candidate additions to _LEAD_MOD_RE:\n"
                        f"# " + " | ".join(f'"{t.split()[0].lower()}"' for t in titles[:3])
                    )
                elif r_val == "leadership" and a_val in ("experienced", "early-career"):
                    action = (
                        f"Consider tightening the leadership pattern that is "
                        f"over-promoting these titles (check _LEAD_STRONG_RE / _LEAD_MOD_RE)"
                    )
                    code_snippet = "# Review patterns: " + ", ".join(f'"{t[:40]}"' for t in titles[:3])
                elif r_val in ("experienced", "leadership") and a_val in ("new-to-labor", "early-career"):
                    action = (
                        f"Consider checking whether these titles contain fellowship/intern/"
                        f"training signals not yet in _NEW_TO_LABOR_TITLE_RE"
                    )
                    code_snippet = "# Candidate additions to _NEW_TO_LABOR_TITLE_RE:\n# " + str(titles[:3])
                else:
                    action = f"Review classify_experience() for '{transition}' transitions"
                    code_snippet = "# Examples: " + ", ".join(f'"{t[:40]}"' for t in titles[:3])

            # ── job_function advice ────────────────────────────────────────
            elif field == "job_function":
                action = (
                    f"Consider adding title keywords for '{a_val}' function to catch: "
                    + ", ".join(f"'{t[:40]}'" for t in titles[:3])
                    + f" (see relevant _RE pattern in classify_jobs_rules.py)"
                )
                code_snippet = (
                    f"# Add to appropriate _RE pattern for '{a_val}' function:\n"
                    f"# r'\\b({'|'.join(w.lower() for t in titles[:3] for w in t.split()[:2])})\\b'"
                )

            # ── employment_type advice ─────────────────────────────────────
            elif field == "employment_type":
                action = (
                    f"Review classify_employment_type() for '{transition}' cases; "
                    f"example titles: " + ", ".join(f"'{t[:40]}'" for t in titles[:3])
                )
                code_snippet = (
                    f"# Add to _{'TEMP' if a_val == 'temporary' else 'PART_TIME' if a_val == 'part-time' else 'CONTRACT'}_TYPE_RE:\n"
                    f"# r'\\b({'|'.join(w.lower() for t in titles[:3] for w in t.split()[:1])})\\b'"
                )

            # ── professional_staff / supervisory advice ────────────────────
            elif field in ("professional_staff", "supervisory"):
                action = (
                    f"Review classify_{field.replace('-', '_')}() for '{transition}' cases; "
                    f"examples: " + ", ".join(f"'{t[:40]}'" for t in titles[:3])
                )
                code_snippet = f"# Review examples: {titles[:3]}"

            # ── location_type advice ───────────────────────────────────────
            else:
                action = (
                    f"Review classify_location_type() for '{transition}' cases; "
                    f"check location_raw patterns: "
                    + ", ".join(f"'{t[:40]}'" for t in titles[:3])
                )
                code_snippet = f"# Review location patterns: {titles[:3]}"

            proposals.append({
                "field":            field,
                "transition":       transition,
                "count":            len(titles),
                "example_titles":   titles[:5],
                "suggested_action": action,
                "proposed_code":    code_snippet,
            })

    return proposals


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def build_report(
    rules_jobs: list,
    api_results: list,
    stats: dict,
    rates: dict,
    failing_fields: list,
    proposals: list,
) -> dict:
    valid_api = sum(1 for r in api_results if r is not None)
    return {
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "model":            MODEL,
        "sample_size":      len(rules_jobs),
        "api_successes":    valid_api,
        "threshold":        AGREEMENT_THRESHOLD,
        "agreement_rates":  rates,
        "failing_fields":   failing_fields,
        "field_details":    {
            field: {
                "agree":    s["agree"],
                "disagree": s["disagree"],
                "examples": s["examples"],
            }
            for field, s in stats.items()
        },
        "proposed_amendments":   proposals,
        # Structured for easy copy-paste into classify_jobs_rules.py
        "proposed_rule_changes": [
            {
                "field":   p["field"],
                "summary": p["suggested_action"],
                "code":    p.get("proposed_code", ""),
                "count":   p["count"],
            }
            for p in proposals
            if p.get("proposed_code")
        ],
    }


def print_summary(rates: dict, failing_fields: list, proposals: list, sample_size: int) -> None:
    print(f"\n── Verification summary ({sample_size} jobs) ───────────────────────")
    for field, rate in rates.items():
        status = "✓" if rate >= AGREEMENT_THRESHOLD else "✗ BELOW 80%"
        print(f"  {field:<20} {rate:.1%}  {status}")
    print("────────────────────────────────────────────────────────")

    if not failing_fields:
        print("  Classification model healthy — all fields ≥ 80% agreement.\n")
        return

    print(f"\n  Failing fields: {', '.join(failing_fields)}")
    print("\n  Proposed rule amendments:")
    for p in proposals:
        print(f"\n  [{p['field']}] {p['transition']}  (×{p['count']})")
        print(f"    {p['suggested_action']}")
        for t in p["example_titles"][:3]:
            print(f"    • {t[:70]}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Monthly classifier verification via Claude API")
    parser.add_argument("--input",  default=str(INPUT_PATH))
    parser.add_argument("--report", default=str(REPORT_PATH))
    parser.add_argument("--sample", type=int, default=30)
    parser.add_argument("--seed",   type=int, default=None, help="Random seed for reproducible sampling")
    args = parser.parse_args()

    # ── 1. Load base job data ──────────────────────────────────────────────
    with open(args.input, encoding="utf-8") as f:
        all_jobs = json.load(f)
    print(f"Loaded {len(all_jobs)} jobs from {args.input}")

    # ── 2. Sample (50% low-confidence, 50% random) ─────────────────────────
    sampled = sample_jobs(all_jobs, n=args.sample, seed=args.seed)
    print(f"Sampled {len(sampled)} jobs for verification "
          f"(≥{args.sample//2} from experience_confidence=0.5 pool)")

    low_conf_count = sum(1 for j in sampled if j.get("experience_confidence") == 0.5)
    print(f"  → {low_conf_count} low-confidence  /  {len(sampled)-low_conf_count} random")

    # ── 3. API re-classification ────────────────────────────────────────────
    print(f"\nRe-classifying via Claude API ({MODEL}) …")
    api_results = asyncio.run(run_api_batch(sampled, concurrency=CONCURRENCY))
    valid = sum(1 for r in api_results if r is not None)
    print(f"\n  API calls: {len(api_results)} total, {valid} successful, "
          f"{len(api_results)-valid} failed")

    # ── 4. Compare ─────────────────────────────────────────────────────────
    stats  = compare(sampled, api_results)
    rates  = agreement_rates(stats)
    failing = [f for f, r in rates.items() if r < AGREEMENT_THRESHOLD]
    proposals = propose_amendments(stats, failing) if failing else []

    # ── 5. Print summary ───────────────────────────────────────────────────
    print_summary(rates, failing, proposals, len(sampled))

    # ── 6. Write report if any field failed ────────────────────────────────
    if failing:
        report = build_report(sampled, api_results, stats, rates, failing, proposals)
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"  Report written to {report_path}")
    else:
        print("  No report written (all fields healthy).")


if __name__ == "__main__":
    main()
