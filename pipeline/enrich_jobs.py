"""
One-time / monthly enrichment: classify jobs via Claude API.

Usage:
    python -m pipeline.enrich_jobs [--input PATH] [--output PATH] [--concurrency N]

Defaults:
    --input        data/classified_jobs.json
    --output       data/enriched_jobs.json   (never overwrites classified_jobs.json)
    --concurrency  10

Reads ANTHROPIC_API_KEY from environment or .env file.
Prints a summary on completion.
"""
import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    # Search .env relative to repo root (two levels up from this file)
    _repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(_repo_root / ".env", override=True)
    load_dotenv()  # also load from cwd as fallback
except ImportError:
    pass

try:
    import anthropic
except ImportError:
    print("ERROR: 'anthropic' package not installed. Run: pip install anthropic>=0.26.0")
    sys.exit(1)

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are a labor-movement job classifier. "
    "Return valid JSON only — no preamble, no markdown fences."
)

USER_TEMPLATE = """\
Classify this union/labor job posting. Return JSON only, no preamble.

Title: {title}
Employer: {employer}
Location: {location_raw}
Description: {description}

Required JSON fields (use exact string values shown):
{{
  "experience_level": "new-to-labor" | "early-career" | "experienced" | "leadership",
  "experience_confidence": 0.9 | 0.7 | 0.5,
  "job_function": "organizing" | "communications" | "political" | "research" | "operations" | "legal" | "finance" | "technology" | "other",
  "location_type": "remote" | "hybrid" | "in-person",
  "location_parsed": {{
    "city": <string or null>,
    "state": <2-letter abbr or null>,
    "region": <e.g. "Bay Area", "Midwest", "Northeast" or null>,
    "near_airports": [<IATA codes>],
    "raw": "{location_raw}"
  }},
  "seniority_signals": [<keywords/phrases from title+description that informed experience_level>],
  "union_affiliation": <parent union acronym e.g. "SEIU", "AFSCME", "CWA", "UAW", "Teamsters", "UFCW", "AFT", "NEA", "IBEW", "USW", "UNITE HERE", "LIUNA", "IBT", "AFL-CIO" or null>,
  "employment_type": "full-time" | "part-time" | "temporary" | "contract",
  "supervisory": true | false,
  "professional_staff": "professional" | "staff",
  "credentials_required": [<list of required credentials e.g. "JD", "CPA", "RN", "LCSW", "PhD", "MBA", "MPH" — empty list if none>],
  "benefits_signals": [<benefits mentioned e.g. "health insurance", "dental", "pension", "401k", "PTO", "vacation" — empty list if none>],
  "years_experience": <minimum years of experience required as integer, or null if not stated>,
  "background_required": [<domain experience signals e.g. "labor movement", "union experience", "campaign experience", "community organizing", "collective bargaining" — empty list if none>],
  "org_size_signal": "small" | "medium" | "large"
}}

experience_level guide:
  new-to-labor  = fellowships, internships, apprenticeships, training programs, "no experience required", "recent graduate" — people entering the labor movement for the first time
  early-career  = junior/entry roles with some prior work experience, clerks, administrative/program assistants, Grade-I titles
  experienced   = mid-level: organizers, specialists, representatives, coordinators, researchers — typically 2–5 years
  leadership    = directors, VPs, executives, chief officers, general counsel — managing teams or setting strategy

experience_confidence guide:
  0.9 = strong signal (clear title keywords: "intern", "fellowship", "director", "executive", or explicit years required)
  0.7 = moderate signal (role type match but ambiguous level, or inferred from description)
  0.5 = weak signal (no clear indicators, best guess)

org_size_signal guide:
  small  = local union, small nonprofit, <50 staff (local chapters, single-city orgs)
  medium = regional union/org, 50–500 staff (state councils, regional affiliates)
  large  = national union, federation, large nonprofit, 500+ staff (AFL-CIO, SEIU national, AFSCME national)"""

VALID_EXP = {"new-to-labor", "early-career", "experienced", "leadership"}
VALID_CONF = {0.9, 0.7, 0.5}
VALID_FUNC = {"organizing", "communications", "political", "research", "operations", "legal", "finance", "technology", "other"}
VALID_LOC_TYPE = {"remote", "hybrid", "in-person"}
VALID_EMP_TYPE = {"full-time", "part-time", "temporary", "contract"}
VALID_PROF_STAFF = {"professional", "staff"}
VALID_ORG_SIZE = {"small", "medium", "large"}


def build_prompt(job: dict) -> str:
    title = (job.get("title") or "").strip()
    employer = (job.get("employer") or "").strip()
    location_raw = (job.get("location_raw") or "").strip()
    desc = (job.get("description") or "").strip()
    desc_truncated = desc[:1500] if desc else "(no description provided)"
    return USER_TEMPLATE.format(
        title=title,
        employer=employer or "(unknown)",
        location_raw=location_raw,
        description=desc_truncated,
    )


def parse_response(text: str) -> Optional[dict]:
    text = text.strip()
    # Strip markdown fences if Claude ignores the instruction
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON object from surrounding text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


def validate_enrichment(data: dict) -> dict:
    """Coerce/default invalid values so the record is always well-formed."""
    exp = data.get("experience_level")
    if exp not in VALID_EXP:
        data["experience_level"] = "experienced"

    conf = data.get("experience_confidence")
    if conf not in VALID_CONF:
        data["experience_confidence"] = 0.5

    func = data.get("job_function")
    if func not in VALID_FUNC:
        data["job_function"] = "other"

    loc_type = data.get("location_type")
    if loc_type not in VALID_LOC_TYPE:
        data["location_type"] = "in-person"

    loc_parsed = data.get("location_parsed")
    if not isinstance(loc_parsed, dict):
        data["location_parsed"] = {"city": None, "state": None, "region": None, "near_airports": [], "raw": ""}

    if not isinstance(data.get("seniority_signals"), list):
        data["seniority_signals"] = []

    # Intelligence card fields — coerce/default
    if data.get("employment_type") not in VALID_EMP_TYPE:
        data["employment_type"] = "full-time"

    if data.get("professional_staff") not in VALID_PROF_STAFF:
        data["professional_staff"] = "staff"

    if not isinstance(data.get("supervisory"), bool):
        data["supervisory"] = False

    if not isinstance(data.get("credentials_required"), list):
        data["credentials_required"] = []

    if not isinstance(data.get("benefits_signals"), list):
        data["benefits_signals"] = []

    if not isinstance(data.get("background_required"), list):
        data["background_required"] = []

    # union_affiliation: string or null
    ua = data.get("union_affiliation")
    if ua is not None and not isinstance(ua, str):
        data["union_affiliation"] = None

    # years_experience: integer or null
    ye = data.get("years_experience")
    if ye is not None:
        try:
            data["years_experience"] = int(ye)
        except (ValueError, TypeError):
            data["years_experience"] = None

    if data.get("org_size_signal") not in VALID_ORG_SIZE:
        data["org_size_signal"] = None

    return data


async def enrich_one(
    client: anthropic.AsyncAnthropic,
    sem: asyncio.Semaphore,
    job: dict,
    idx: int,
    total: int,
) -> dict:
    prompt = build_prompt(job)
    for attempt in range(2):
        try:
            async with sem:
                response = await client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
            text = response.content[0].text if response.content else ""
            parsed = parse_response(text)
            if parsed is None:
                raise ValueError(f"Could not parse JSON from response: {text[:200]}")
            validated = validate_enrichment(parsed)
            if (idx + 1) % 50 == 0 or idx == 0:
                print(f"  [{idx + 1}/{total}] {job.get('title', '')[:60]}")
            return {**job, **validated, "_enriched": True}
        except Exception as e:
            if attempt == 0:
                # Back off longer on rate-limit errors (429)
                wait = 15 if "rate_limit" in str(e).lower() or "429" in str(e) else 3
                await asyncio.sleep(wait)
                continue
            print(f"  FAILED [{idx + 1}/{total}] {job.get('title', '')[:50]}: {e}")
            # Return job with failure marker and null enrichment fields
            return {
                **job,
                "experience_level": None,
                "experience_confidence": None,
                "job_function": None,
                "location_type": None,
                "location_parsed": None,
                "seniority_signals": [],
                "_enriched": False,
                "_enrich_error": str(e),
            }


async def run_enrichment(jobs: list, concurrency: int) -> list:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    client = anthropic.AsyncAnthropic(api_key=api_key)
    sem = asyncio.Semaphore(concurrency)
    total = len(jobs)

    print(f"Enriching {total} jobs with concurrency={concurrency}…")
    tasks = [enrich_one(client, sem, job, i, total) for i, job in enumerate(jobs)]
    results = await asyncio.gather(*tasks)
    return list(results)


def print_summary(results: list) -> None:
    total = len(results)
    succeeded = sum(1 for r in results if r.get("_enriched"))
    failed = total - succeeded

    exp_counts: Counter = Counter(r.get("experience_level") for r in results if r.get("_enriched"))
    func_counts: Counter = Counter(r.get("job_function") for r in results if r.get("_enriched"))
    loc_counts: Counter = Counter(r.get("location_type") for r in results if r.get("_enriched"))

    print(f"\n{'='*60}")
    print(f"Total jobs:       {total}")
    print(f"Succeeded:        {succeeded}")
    print(f"Failed:           {failed}")
    print(f"\nexperience_level: {dict(exp_counts.most_common())}")
    print(f"job_function:     {dict(func_counts.most_common())}")
    print(f"location_type:    {dict(loc_counts.most_common())}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Enrich classified jobs via Claude API")
    parser.add_argument("--input",       default="data/classified_jobs.json")
    parser.add_argument("--output",      default="data/enriched_jobs.json")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--resume",      action="store_true",
                        help="Resume: skip jobs already successfully enriched in --output")
    args = parser.parse_args()

    if Path(args.output).resolve() == Path(args.input).resolve():
        print("ERROR: --output must differ from --input to protect classified_jobs.json")
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        jobs = json.load(f)

    # Resume: carry forward already-enriched records, only re-process failures
    prior: dict = {}
    if args.resume and Path(args.output).exists():
        with open(args.output, encoding="utf-8") as f:
            prior_list = json.load(f)
        prior = {r["job_id"]: r for r in prior_list if r.get("_enriched") and r.get("job_id")}
        skip = len(prior)
        jobs_to_run = [j for j in jobs if j.get("job_id") not in prior]
        print(f"Resume: keeping {skip} already-enriched records, re-running {len(jobs_to_run)}")
    else:
        jobs_to_run = jobs

    new_results = asyncio.run(run_enrichment(jobs_to_run, args.concurrency))

    # Merge: prior successes + new results, preserving original order
    if prior:
        new_by_id = {r.get("job_id"): r for r in new_results}
        results = []
        for j in jobs:
            jid = j.get("job_id")
            if jid in prior:
                results.append(prior[jid])
            elif jid in new_by_id:
                results.append(new_by_id[jid])
            else:
                results.append(j)
    else:
        results = new_results

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(results)} records → {args.output}")
    print_summary(results)


if __name__ == "__main__":
    main()
