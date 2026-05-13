"""
Arena progressive jobs board ingestor.
Target: careers.arena.run (corrected from arena.run/jobs which 404s)

Arena is a Next.js app. Strategy:
  1. Look for __NEXT_DATA__ JSON blob embedded in the page
  2. If found, extract job listing array
  3. Otherwise, try HTML card parsing
  4. If 0 jobs from static HTML, log JS-rendering warning
"""
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from pipeline.ingestors.router import FetchError, RATE_LIMIT_SLEEP, get_html
from pipeline.ingestors import generic

BOARD_KEY = "arena"
SOURCE_BOARD = "Arena"

_CANONICAL_BOARD_URL = "https://careers.arena.run/jobs"


def ingest(url):
    """Entry point for Arena URLs."""
    try:
        html = get_html(url, timeout=30)
    except FetchError as e:
        print(f"ERROR [arena]: {e}")
        return []

    # 1. Try __NEXT_DATA__ embedded JSON
    jobs = _find_next_data(html, url)
    if jobs is not None:
        print(f"INFO [arena]: Found __NEXT_DATA__ with {len(jobs)} jobs.")
        return jobs

    # 2. HTML card parsing
    jobs = _parse_html_cards(html, url)
    if jobs:
        print(f"INFO [arena]: Parsed {len(jobs)} jobs from HTML cards.")
        return jobs

    # 3. Graceful failure: check for JS bundle indicators
    soup = BeautifulSoup(html, "lxml")
    has_bundles = bool(soup.find_all("script", src=re.compile(r'\.(chunk|bundle|main)\.[a-f0-9]+\.js')))
    if has_bundles:
        print(
            "WARNING [arena]: Page appears JavaScript-rendered. "
            "Static scraping found 0 jobs. "
            "The __NEXT_DATA__ blob was not found or contained no job listings. "
            "Try pasting individual job URLs."
        )
    else:
        print(f"WARNING [arena]: Found 0 jobs on {url}.")

    return []


def _find_next_data(html_text, base_url):
    """
    Parse window.__NEXT_DATA__ JSON blob if present.
    Returns list of raw job dicts or None if no blob found.
    """
    m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>\s*(\{.*?\})\s*</script>', html_text, re.S)
    if not m:
        m = re.search(r'__NEXT_DATA__\s*=\s*(\{.*?\})\s*;?\s*(?=\n|<)', html_text, re.S)
    if not m:
        return None

    try:
        outer = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    # Drill into likely locations for job listings
    props = outer.get("props", {}).get("pageProps", {})
    for key in ("jobs", "positions", "listings", "data", "results", "openings"):
        val = props.get(key)
        if isinstance(val, list) and val:
            return _parse_job_records(val, base_url)

    # Recurse one level deeper
    for top_key in props:
        sub = props[top_key]
        if isinstance(sub, dict):
            for key in ("jobs", "positions", "listings", "data"):
                val = sub.get(key)
                if isinstance(val, list) and val:
                    return _parse_job_records(val, base_url)

    return None


def _parse_job_records(records, base_url):
    """Map job records from __NEXT_DATA__ to raw schema."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = []
    for rec in records:
        if not isinstance(rec, dict):
            continue

        title = (
            rec.get("title") or rec.get("jobTitle") or rec.get("name")
            or rec.get("positionTitle")
        )
        if not title:
            continue

        location_raw = (
            rec.get("location") or rec.get("jobLocation") or rec.get("city")
        )
        if not location_raw:
            city = rec.get("city", "")
            state = rec.get("state", "") or rec.get("stateAbbr", "")
            location_raw = f"{city}, {state}".strip(", ") if (city or state) else None
        if not location_raw and rec.get("remote"):
            location_raw = "Remote"

        slug = rec.get("slug") or rec.get("id") or rec.get("jobId") or ""
        job_url = rec.get("url") or rec.get("link") or rec.get("applyUrl")
        if not job_url and slug:
            job_url = urljoin(base_url, f"/jobs/{slug}")
        if not job_url:
            job_url = base_url

        employer = rec.get("organization") or rec.get("employer") or rec.get("company")

        results.append({
            "title": str(title).strip(),
            "location_raw": str(location_raw).strip() if location_raw else "Unknown",
            "source_url": job_url,
            "source_board": SOURCE_BOARD,
            "employer": str(employer).strip() if employer else None,
            "salary": rec.get("salary") or rec.get("compensation"),
            "description": str(rec.get("description", ""))[:600] or None,
            "posted_date": rec.get("datePosted") or rec.get("postedAt") or rec.get("createdAt"),
            "scraped_at": now,
            "confidence": 0.85,
        })

    return results


def _parse_html_cards(html_text, base_url):
    """
    Fallback: look for visible job card elements in the HTML.
    Tries common CSS class patterns for Next.js/React job boards.
    """
    soup = BeautifulSoup(html_text, "lxml")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = []

    # Common job-card selector patterns
    card_selectors = [
        "[class*='job-card']",
        "[class*='JobCard']",
        "[class*='job-listing']",
        "[class*='JobListing']",
        "[class*='posting']",
        "article[class*='job']",
        "li[class*='job']",
    ]

    cards = []
    for sel in card_selectors:
        cards = soup.select(sel)
        if cards:
            break

    for card in cards:
        title_el = card.find(["h2", "h3", "h4", "strong", "[class*='title']"])
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue

        location_el = card.find(["[class*='location']", "[class*='city']"])
        location_raw = location_el.get_text(strip=True) if location_el else None
        if not location_raw:
            location_raw = generic._extract_location_from_text(card.get_text(" ", strip=True))

        link = card.find("a", href=True)
        job_url = urljoin(base_url, link["href"]) if link else base_url

        results.append({
            "title": title,
            "location_raw": location_raw or "Unknown",
            "source_url": job_url,
            "source_board": SOURCE_BOARD,
            "employer": None,
            "scraped_at": now,
            "confidence": 0.60,
        })

    return results
