"""
Matt Lockshin Job Board ingestor.
Target: mattlockshin.com/job-board (Webflow CMS site)

NOTE: As of 2026-05-13, mattlockshin.com has an SSL misconfiguration that
prevents normal HTTPS connections from Python's ssl module (LibreSSL 2.8.3).
The ingestor retries with verify=False as a fallback.

Webflow CMS boards typically render collection items as <div class="w-dyn-item">.
JSON-LD is tried first; Webflow HTML structure is the fallback.
"""
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from pipeline.ingestors.router import FetchError, DEFAULT_HEADERS, RATE_LIMIT_SLEEP, get_html
from pipeline.ingestors import generic

BOARD_KEY = "lockshin"
SOURCE_BOARD = "Matt Lockshin Job Board"


def ingest(url):
    """Entry point for Lockshin URLs. SSL errors are handled by get_html fallback."""
    # Attempt JSON-LD first (some Webflow sites include it)
    jobs = generic.extract_single_job(url)
    if jobs:
        for job in jobs:
            job["source_board"] = SOURCE_BOARD
        return jobs

    # HTML Webflow fallback
    try:
        html = get_html(url, verify=False)
    except FetchError as e:
        print(f"ERROR [lockshin]: {e}")
        return []

    return _parse_webflow_html(html, url)


def _parse_webflow_html(html_text, base_url):
    """
    Parse Webflow CMS collection list.
    Webflow collection items are wrapped in <div class="w-dyn-item"> divs.
    """
    soup = BeautifulSoup(html_text, "lxml")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = []
    base = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"

    # Webflow dynamic list items
    items = soup.select(".w-dyn-item")

    if not items:
        # Try fallback selectors for other CMS patterns
        items = soup.select(
            "article, .job-post, .job-item, .listing-item, "
            "[class*='job'], [class*='position'], [class*='opening']"
        )

    if not items:
        # Last resort: use generic board extraction
        print(f"INFO [lockshin]: No Webflow items found, trying generic extraction.")
        return generic.ingest(base_url)

    for item in items:
        # Title: first heading or strong element
        title_el = item.find(["h1", "h2", "h3", "h4", "strong"])
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue

        # Employer: look for org/company text
        employer = _find_field(item, ["organization", "employer", "company", "org", "union"])

        # Location
        location_raw = _find_field(item, ["location", "city", "state", "where"])
        if not location_raw:
            location_raw = generic._extract_location_from_text(item.get_text(" ", strip=True))

        # Link to detail page
        link = item.find("a", href=True)
        job_url = urljoin(base, link["href"]) if link else base_url

        confidence = 0.75 if location_raw else 0.50

        job = {
            "title": title,
            "location_raw": location_raw or "Unknown",
            "source_url": job_url,
            "source_board": SOURCE_BOARD,
            "employer": employer,
            "scraped_at": now,
            "confidence": confidence,
        }

        # Optionally fetch detail page for description + salary
        if job_url != base_url:
            time.sleep(RATE_LIMIT_SLEEP)
            try:
                detail_html = get_html(job_url, verify=False)
                _enrich_from_detail(job, detail_html, job_url)
            except FetchError as e:
                pass  # Keep partial data

        results.append(job)

    print(f"INFO [lockshin]: Extracted {len(results)} jobs from Webflow board.")
    return results


def _find_field(item_soup, field_names):
    """Look for text in elements whose class or data attributes contain field keywords."""
    for name in field_names:
        # By class
        el = item_soup.find(class_=re.compile(name, re.I))
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
        # By label pattern: "Location: ..."
        label_pat = re.compile(rf'{name}\s*:\s*([^\n\r]{{3,60}})', re.I)
        m = label_pat.search(item_soup.get_text(" ", strip=True))
        if m:
            return m.group(1).strip()
    return None


def _enrich_from_detail(job, detail_html, url):
    """Fetch description and salary from a detail page."""
    soup = BeautifulSoup(detail_html, "lxml")
    full_text = soup.get_text(" ", strip=True)

    if not job.get("description"):
        # Grab a meaningful block of text (skip header area)
        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 50]
        job["description"] = " ".join(paras)[:600] or None

    if not job.get("salary"):
        job["salary"] = generic._extract_salary_from_text(full_text)

    if not job.get("employer"):
        job["employer"] = generic._extract_employer_from_text(full_text)
