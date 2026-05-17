"""
GainPower Career Center ingestor.
Target: careercenter.gainpower.org

NOTE: As of 2026-05-13 this domain returns 403 for automated requests
even with browser User-Agent headers. The ingestor is built to spec but
will fail gracefully with an informative error until/unless the site
changes its access policy or credentials are available.
"""
import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from pipeline.ingestors.router import FetchError, RATE_LIMIT_SLEEP, get_html
from pipeline.ingestors import generic

BOARD_KEY = "gain_power"
SOURCE_BOARD = "GainPower Career Center"

_LISTING_URL_RE = re.compile(r'/job/\d+|/job/[a-z0-9-]+', re.I)


def ingest(url):
    """Entry point. Detects board vs single, dispatches."""
    parsed = urlparse(url)
    # If path looks like a single job listing, extract single
    if _LISTING_URL_RE.search(parsed.path):
        return _parse_job_page(url)

    # Otherwise treat as board
    return _fetch_listings(url)


def _fetch_listings(url):
    """Fetch board index, find job links, parse each."""
    try:
        html = get_html(url)
    except FetchError as e:
        print(f"ERROR [gain_power]: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    # GainPower ATS uses standard job link patterns
    seen = set()
    job_urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        abs_url = urljoin(base, href)
        if _LISTING_URL_RE.search(urlparse(abs_url).path) and abs_url not in seen:
            seen.add(abs_url)
            job_urls.append(abs_url)

    # Fall back to generic board extraction if no ATS-style links found
    if not job_urls:
        print(f"INFO [gain_power]: No ATS-style job links found, trying generic board extraction.")
        return generic.extract_board_jobs(url)

    print(f"INFO [gain_power]: Found {len(job_urls)} job listings.")
    results = []
    for i, job_url in enumerate(job_urls):
        print(f"  [{i+1}/{len(job_urls)}] {job_url}")
        time.sleep(RATE_LIMIT_SLEEP)
        results.extend(_parse_job_page(job_url))

    return results


def _parse_job_page(url):
    """Fetch single job page: JSON-LD first, then HTML selectors."""
    # Try JSON-LD first via generic
    jobs = generic.extract_single_job(url)
    if jobs:
        for job in jobs:
            job["source_board"] = SOURCE_BOARD
        return jobs

    # HTML fallback: GainPower ATS typical structure
    try:
        html = get_html(url)
    except FetchError as e:
        print(f"  WARNING [gain_power]: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")

    title = None
    for sel in ["h1.job-title", "h1", ".job-title", "[itemprop='title']"]:
        el = soup.select_one(sel)
        if el:
            title = el.get_text(strip=True)
            break

    if not title:
        return []

    location_raw = None
    for sel in [".job-location", "[itemprop='jobLocation']", ".location"]:
        el = soup.select_one(sel)
        if el:
            location_raw = el.get_text(strip=True)
            break

    if not location_raw:
        location_raw = generic._extract_location_from_text(soup.get_text(" ", strip=True)) or "Unknown"

    employer = None
    for sel in [".company-name", "[itemprop='hiringOrganization']", ".employer"]:
        el = soup.select_one(sel)
        if el:
            employer = el.get_text(strip=True)
            break

    desc_el = soup.select_one(".job-description, #job-description, [itemprop='description']")
    description = desc_el.get_text(" ", strip=True)[:600] if desc_el else None

    confidence = 0.85 if location_raw and location_raw != "Unknown" else 0.70

    from pipeline.ingestors.generic import _now
    return [{
        "title": title,
        "location_raw": location_raw,
        "source_url": url,
        "source_board": SOURCE_BOARD,
        "employer": employer,
        "description": description,
        "scraped_at": _now(),
        "confidence": confidence,
    }]
