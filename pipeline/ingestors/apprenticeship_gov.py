"""
Apprenticeship.gov Job Finder ingestor.
Target: www.apprenticeship.gov/apprenticeship-job-finder

Strategy:
  1. Probe for a JSON API endpoint (Accept: application/json)
  2. If the API returns structured JSON job records, parse those
  3. If the page is HTML/React-rendered, log a warning and return []

As of 2026-05-13 the job finder page loads 200 OK but is likely React-rendered
(the job results appear after JS execution). The API probe will attempt to find
a direct data endpoint; if it fails, the HTML fallback will check for embedded
JSON data in script tags before giving up.
"""
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from pipeline.ingestors.router import FetchError, DEFAULT_HEADERS, RATE_LIMIT_SLEEP, get_html
from pipeline.ingestors import generic

BOARD_KEY = "apprenticeship_gov"
SOURCE_BOARD = "Apprenticeship.gov Job Finder"

# Known or likely API endpoints to probe
_API_CANDIDATES = [
    "https://www.apprenticeship.gov/apprenticeship-job-finder/api/jobs",
    "https://www.apprenticeship.gov/api/v1/jobs",
    "https://www.apprenticeship.gov/api/jobs",
]


def ingest(url):
    """Entry point: probe API, then HTML, then log graceful failure."""
    # 1. Try API probe
    jobs = _probe_api(url)
    if jobs is not None:
        print(f"INFO [apprenticeship_gov]: API probe succeeded, got {len(jobs)} jobs.")
        return jobs

    # 2. Try HTML/embedded-JSON parse
    jobs = _parse_html(url)
    return jobs


def _probe_api(url):
    """
    Try fetching known API endpoints with JSON Accept header.
    Returns list of raw job dicts or None if no API found.
    """
    api_headers = dict(DEFAULT_HEADERS)
    api_headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
    api_headers["X-Requested-With"] = "XMLHttpRequest"

    for api_url in _API_CANDIDATES:
        try:
            resp = requests.get(api_url, headers=api_headers, timeout=15, allow_redirects=True)
            ct = resp.headers.get("Content-Type", "")
            if resp.ok and "json" in ct:
                data = resp.json()
                jobs = _parse_api(data, api_url)
                if jobs:
                    print(f"INFO [apprenticeship_gov]: Found API at {api_url}")
                    return jobs
        except Exception as e:
            pass  # Silently try next candidate

    return None


def _parse_api(data, source_url):
    """Map API response fields to raw job schema."""
    if isinstance(data, dict):
        # Unwrap common envelope shapes: {"jobs": [...]} or {"data": [...]}
        records = (
            data.get("jobs")
            or data.get("data")
            or data.get("results")
            or data.get("items")
            or (list(data.values())[0] if len(data) == 1 else None)
        )
        if not isinstance(records, list):
            return []
    elif isinstance(data, list):
        records = data
    else:
        return []

    results = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for rec in records:
        if not isinstance(rec, dict):
            continue

        title = (
            rec.get("title") or rec.get("jobTitle") or rec.get("job_title")
            or rec.get("positionTitle") or rec.get("name")
        )
        if not title:
            continue

        location_raw = (
            rec.get("location") or rec.get("jobLocation") or rec.get("city")
            or rec.get("address")
        )
        if not location_raw:
            city = rec.get("city", "")
            state = rec.get("state", "") or rec.get("stateAbbr", "")
            if city or state:
                location_raw = f"{city}, {state}".strip(", ")

        if not location_raw:
            location_raw = "Unknown"

        employer = (
            rec.get("employer") or rec.get("company") or rec.get("organization")
            or rec.get("sponsor") or rec.get("programSponsor")
        )

        job_id = rec.get("id") or rec.get("jobId") or rec.get("job_id") or ""
        job_url = (
            rec.get("url") or rec.get("link") or rec.get("applyUrl")
            or (f"{source_url}?id={job_id}" if job_id else source_url)
        )

        salary = rec.get("salary") or rec.get("wage") or rec.get("hourlyWage")
        if isinstance(salary, (int, float)):
            salary = f"${salary}/hr"

        results.append({
            "title": str(title).strip(),
            "location_raw": str(location_raw).strip(),
            "source_url": job_url,
            "source_board": SOURCE_BOARD,
            "employer": str(employer).strip() if employer else None,
            "salary": str(salary).strip() if salary else None,
            "description": str(rec.get("description", ""))[:600] or None,
            "posted_date": rec.get("datePosted") or rec.get("postedDate"),
            "scraped_at": now,
            "confidence": 0.90,
        })

    return results


def _parse_html(url):
    """
    HTML / embedded-data fallback.
    Checks for Next.js __NEXT_DATA__ or similar embedded JSON before giving up.
    """
    try:
        html = get_html(url)
    except FetchError as e:
        print(f"ERROR [apprenticeship_gov]: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")

    # Look for embedded JSON data in script tags
    for script in soup.find_all("script"):
        text = script.string or ""
        if "__NEXT_DATA__" in text or '"jobs"' in text:
            data = _extract_embedded_json(text)
            if data:
                jobs = _parse_api(data, url)
                if jobs:
                    print(f"INFO [apprenticeship_gov]: Found embedded JSON data with {len(jobs)} jobs.")
                    return jobs

    # Check if page is JS-rendered with no static job content
    page_text = soup.get_text()
    has_bundles = bool(soup.find_all("script", src=re.compile(r'\.(chunk|bundle|main)\.[a-f0-9]+\.js')))
    job_keywords = re.findall(r'\b(apprenticeship|jobs?|openings?)\b', page_text, re.I)

    if has_bundles and len(job_keywords) < 5:
        print(
            "WARNING [apprenticeship_gov]: Page appears JavaScript-rendered. "
            "Static HTML has no job records. "
            "The API probe found no endpoint. No jobs extracted. "
            "Consider: (1) check for updated API URL, (2) paste individual job URLs."
        )
        return []

    # Try generic HTML extraction as last resort
    jobs = generic._extract_single_from_html(html, url)
    if not jobs:
        print(f"WARNING [apprenticeship_gov]: Could not extract jobs from {url}.")
    return jobs


def _extract_embedded_json(script_text):
    """Try to parse JSON from a script tag containing __NEXT_DATA__ or similar."""
    # __NEXT_DATA__ pattern
    m = re.search(r'__NEXT_DATA__\s*=\s*(\{.*?\})\s*;?\s*(?:\n|$)', script_text, re.S)
    if m:
        try:
            outer = json.loads(m.group(1))
            # Drill into props.pageProps.jobs or similar
            props = outer.get("props", {}).get("pageProps", {})
            for key in ("jobs", "data", "listings", "results", "items"):
                if key in props and isinstance(props[key], list):
                    return props[key]
            return outer
        except json.JSONDecodeError:
            pass

    # Bare JSON assignment
    m = re.search(r'window\.__(?:DATA|JOBS|STATE)__\s*=\s*(\{.*?\})\s*;', script_text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    return None
