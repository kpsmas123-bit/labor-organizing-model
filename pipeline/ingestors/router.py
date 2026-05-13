"""
URL ingestion router: detect which board a URL belongs to, dispatch to the
right ingestor, and provide shared HTTP utilities.

Usage:
    from pipeline.ingestors.router import ingest, detect_board
    jobs = ingest("https://miaflcio.org/jobs/")
"""
import time
import urllib.robotparser
import warnings

import requests
from urllib.parse import urlparse

# Suppress LibreSSL/urllib3 warnings in Python 3.9 on macOS
warnings.filterwarnings("ignore", category=requests.packages.urllib3.exceptions.NotOpenSSLWarning, module="urllib3")

RATE_LIMIT_SLEEP = 2.0  # seconds between board-page requests

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Board URL corrections (from live verification 2026-05-13):
#   arena.run/jobs → 404; canonical is careers.arena.run/jobs
#   careercenter.gainpower.org → 403 (blocks scrapers), built but may fail
#   mattlockshin.com → SSL error, built but may fail
SUPPORTED_BOARDS = [
    {
        "key": "gain_power",
        "name": "GainPower Career Center",
        "url": "https://careercenter.gainpower.org",
        "note": "May block automated requests (403); try pasting individual job URLs",
    },
    {
        "key": "apprenticeship_gov",
        "name": "Apprenticeship.gov Job Finder",
        "url": "https://www.apprenticeship.gov/apprenticeship-job-finder",
    },
    {
        "key": "arena",
        "name": "Arena Progressive Jobs",
        # Corrected from arena.run/jobs (404) → careers.arena.run/jobs (live)
        "url": "https://careers.arena.run/jobs",
    },
    {
        "key": "lockshin",
        "name": "Matt Lockshin Job Board",
        "url": "https://mattlockshin.com/job-board",
        "note": "SSL misconfiguration on host; may fail with certificate error",
    },
    {
        "key": "aflcio_state",
        "name": "AFL-CIO State/Regional Sites",
        "url": "https://*.aflcio.org",
    },
]


class RobotsDisallowedError(Exception):
    pass


class FetchError(Exception):
    pass


def detect_board(url):
    """Return board key string or None. Corrected for live URL changes."""
    parsed = urlparse(url)
    hostname = parsed.netloc.lower().lstrip("www.")

    if "careercenter.gainpower.org" in hostname or hostname == "careercenter.gainpower.org":
        return "gain_power"
    if "apprenticeship.gov" in hostname:
        return "apprenticeship_gov"
    # Corrected: arena moved to careers.arena.run
    if "careers.arena.run" in hostname or hostname == "arena.run":
        return "arena"
    if "mattlockshin.com" in hostname:
        return "lockshin"
    # State AFL-CIO sites: ends with aflcio.org
    if hostname.endswith("aflcio.org"):
        return "aflcio_state"

    return None


def check_robots(url):
    """
    Raise RobotsDisallowedError if robots.txt disallows the URL.
    If robots.txt is unreachable, log a warning and proceed.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception as e:
        print(f"WARNING: Could not fetch robots.txt from {robots_url}: {e}. Proceeding cautiously.")
        return

    agent = DEFAULT_HEADERS["User-Agent"]
    if not rp.can_fetch(agent, url) and not rp.can_fetch("*", url):
        raise RobotsDisallowedError(f"robots.txt at {robots_url} disallows {url}")


def get_html(url, sleep_before=False, timeout=20, verify=True):
    """
    Fetch url and return response text.
    Raises FetchError on HTTP error or network failure.
    """
    if sleep_before:
        time.sleep(RATE_LIMIT_SLEEP)

    try:
        resp = requests.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            allow_redirects=True,
            verify=verify,
        )
    except requests.exceptions.SSLError as e:
        # Try without SSL verification as a fallback (with warning)
        print(f"WARNING: SSL error for {url}: {e}. Retrying with verify=False.")
        try:
            resp = requests.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=timeout,
                allow_redirects=True,
                verify=False,
            )
        except Exception as e2:
            raise FetchError(f"Failed to fetch {url}: {e2}") from e2
    except requests.exceptions.Timeout:
        raise FetchError(f"Timeout fetching {url}")
    except requests.exceptions.RequestException as e:
        raise FetchError(f"Network error fetching {url}: {e}") from e

    if resp.status_code == 401 or resp.status_code == 403:
        raise FetchError(f"HTTP {resp.status_code} — {url} may require authentication or blocks scraping")
    if resp.status_code == 404:
        raise FetchError(f"HTTP 404 — page not found: {url}")
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status_code} fetching {url}")

    return resp.text


def ingest(url, mode="auto"):
    """
    Main entry point. Returns list of raw job dicts (each with a 'confidence' key).

    mode:
      'auto'   — detect board then dispatch; falls back to generic
      'single' — force single-job extraction from this URL
      'board'  — force board-scan from this URL
    """
    from pipeline.ingestors import generic

    check_robots(url)

    board_key = detect_board(url)

    if mode == "single":
        return generic.extract_single_job(url)

    if mode == "board":
        return generic.extract_board_jobs(url)

    # mode == 'auto'
    if board_key == "gain_power":
        from pipeline.ingestors import gain_power
        return gain_power.ingest(url)
    elif board_key == "apprenticeship_gov":
        from pipeline.ingestors import apprenticeship_gov
        return apprenticeship_gov.ingest(url)
    elif board_key == "arena":
        from pipeline.ingestors import arena
        return arena.ingest(url)
    elif board_key == "lockshin":
        from pipeline.ingestors import lockshin
        return lockshin.ingest(url)
    elif board_key == "aflcio_state":
        from pipeline.ingestors import aflcio_state
        return aflcio_state.ingest(url)
    else:
        return generic.ingest(url)
