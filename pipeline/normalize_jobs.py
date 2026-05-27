"""
Normalize raw scraped job dicts into the canonical pipeline schema.

Usage:
    python -m pipeline.normalize_jobs [--input PATH] [--output PATH] [--rejected PATH]

Defaults:
    --input    data/raw_jobs.json
    --output   data/normalized_jobs.json
    --rejected data/rejected_jobs.json
"""
import argparse
import hashlib
import html
import json
import re
import sys
from collections import Counter

from pipeline.parsers.location import parse_location
from pipeline.parsers.salary import parse_salary

_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'[ \t]+')
_NEWLINE_RE = re.compile(r'\n{3,}')


def _strip_html(text: str) -> str:
    if not text:
        return text
    text = html.unescape(text)
    text = _TAG_RE.sub(' ', text)
    text = _WS_RE.sub(' ', text)
    text = _NEWLINE_RE.sub('\n\n', text)
    return text.strip()


def _norm_ws(value):
    """Collapse whitespace in a string; pass through non-strings unchanged."""
    if not isinstance(value, str):
        return value
    return _WS_RE.sub(' ', value).strip() or None


def _build_source_url(raw: dict):
    # Explicit source_url field takes priority
    if raw.get('source_url'):
        return raw['source_url'].strip()
    # Construct from scraper job_id for unionjobs.com
    board = (raw.get('source') or raw.get('source_board') or '').lower()
    if 'unionjobs' in board and raw.get('job_id'):
        return f"https://www.unionjobs.com/listing.php?id={raw['job_id']}"
    # Fall back to apply_url
    if raw.get('apply_url'):
        return raw['apply_url'].strip()
    return None


def normalize_job(raw: dict) -> tuple:
    """
    Returns (normalized_job, None) on success or (None, rejection_reason) on failure.
    """
    # --- Required field checks ---
    title = _norm_ws(raw.get('title') or '') or ''

    location_raw = _norm_ws(raw.get('location_raw') or raw.get('location') or '') or ''

    source_board = _norm_ws(
        raw.get('source_board') or raw.get('source') or ''
    )
    if not source_board:
        return None, "missing source_board"

    source_url = _build_source_url(raw)
    if not source_url:
        return None, "missing source_url"

    # --- Derived fields ---
    job_id = hashlib.sha1(source_url.encode()).hexdigest()[:12]

    loc = parse_location(location_raw)
    # Fall back to scraper-provided state_abbr if parser returned None
    state_abbr = loc['state_abbr'] or _norm_ws(raw.get('state_abbr') or '')

    salary_raw = _norm_ws(raw.get('salary') or raw.get('salary_raw') or '')
    sal = parse_salary(salary_raw) if salary_raw else {"salary_min": None, "salary_max": None, "salary_period": None}

    description = _strip_html(raw.get('description') or '')

    job = {
        # Required
        "title": title,
        "location_raw": location_raw,
        "source_url": source_url,
        "source_board": source_board,
        # Optional pass-through
        "employer": _norm_ws(raw.get('employer') or raw.get('organization') or ''),
        "salary_raw": salary_raw or None,
        "sector": raw.get('sector') or None,
        "role_type": raw.get('role_type') or None,
        "exp_level": raw.get('exp_level') or None,
        "special_requirements": raw.get('special_requirements') or [],
        "posted_date": raw.get('posted_date') or raw.get('date_posted') or None,
        # Derived
        "job_id": job_id,
        "city": loc['city'],
        "state_abbr": state_abbr or None,
        "is_remote": loc['is_remote'],
        "salary_min": sal['salary_min'],
        "salary_max": sal['salary_max'],
        "salary_period": sal['salary_period'],
        "description": description or None,
        "scraped_at": raw.get('scraped_at') or None,
    }
    return job, None


def main():
    parser = argparse.ArgumentParser(description="Normalize raw job dicts to canonical schema")
    parser.add_argument('--input',    default='data/raw_jobs.json')
    parser.add_argument('--output',   default='data/normalized_jobs.json')
    parser.add_argument('--rejected', default='data/rejected_jobs.json')
    args = parser.parse_args()

    with open(args.input, encoding='utf-8') as f:
        raw_jobs = json.load(f)

    # Handle wrapper object with metadata (e.g. jobs_data.json format)
    if isinstance(raw_jobs, dict):
        raw_jobs = raw_jobs.get('jobs') or raw_jobs.get('listings') or list(raw_jobs.values())

    accepted = []
    rejected = []
    rejection_counts: Counter = Counter()

    for raw in raw_jobs:
        job, reason = normalize_job(raw)
        if job:
            accepted.append(job)
        else:
            rejected.append({"job": raw, "reason": reason})
            rejection_counts[reason] += 1

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(accepted, f, indent=2, ensure_ascii=False)

    with open(args.rejected, 'w', encoding='utf-8') as f:
        json.dump(rejected, f, indent=2, ensure_ascii=False)

    reasons_str = ', '.join(f'"{r}": {c}' for r, c in rejection_counts.most_common())
    print(f"Accepted: {len(accepted)} | Rejected: {len(rejected)} | Rejection reasons: {{{reasons_str}}}")


if __name__ == '__main__':
    main()
