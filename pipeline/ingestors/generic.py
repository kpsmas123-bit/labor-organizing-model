"""
Generic URL ingestor: JSON-LD → Open Graph → HTML heuristics cascade.
Used as a fallback for any URL not matched by a named board ingestor,
and called directly by named ingestors as a fallback strategy.
"""
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from pipeline.ingestors.router import FetchError, RATE_LIMIT_SLEEP, get_html

# URL path segments that suggest a job listing page
_JOB_URL_PATTERNS = re.compile(
    r'/(job|jobs|position|positions|opening|openings|listing|listings|'
    r'career|careers|vacancy|vacancies|opportunity|opportunities|apply|posting|postings)(/|$|\?|#)',
    re.I,
)

# Minimum number of job-like links to treat a page as a board (not a single job)
_BOARD_LINK_THRESHOLD = 8

# Board path/query signals in the URL itself
_BOARD_URL_RE = re.compile(
    r'/(jobs|careers|openings|listings|positions|vacancies|opportunities)(/|$|\?)',
    re.I,
)
_BOARD_QUERY_RE = re.compile(r'[?&](page|category|filter|search|q|keyword)=', re.I)


def ingest(url):
    """Auto-detect single-job vs board page, dispatch accordingly."""
    try:
        html_text = get_html(url)
    except FetchError as e:
        print(f"ERROR: {e}")
        return []

    if _is_board_page(html_text, url):
        print(f"Detected board page: {url}")
        return _extract_board_from_html(html_text, url)
    else:
        print(f"Detected single job page: {url}")
        return _extract_single_from_html(html_text, url)


def extract_single_job(url):
    """Force single-job extraction from the given URL."""
    try:
        html_text = get_html(url)
    except FetchError as e:
        print(f"ERROR: {e}")
        return []
    return _extract_single_from_html(html_text, url)


def extract_board_jobs(url):
    """Force board-scan from the given URL."""
    try:
        html_text = get_html(url)
    except FetchError as e:
        print(f"ERROR: {e}")
        return []
    return _extract_board_from_html(html_text, url)


def _is_board_page(html_text, url):
    """True if the page looks like a listing page rather than a single job."""
    parsed = urlparse(url)
    path = parsed.path

    # URL-level signals
    if _BOARD_URL_RE.search(path):
        return True
    if _BOARD_QUERY_RE.search(parsed.query):
        return True

    # Link-count signal
    job_links = _find_job_links(html_text, url)
    if len(job_links) >= _BOARD_LINK_THRESHOLD:
        return True

    return False


# Known ATS/job board domains — cross-domain links to these are valid job links
_ATS_DOMAINS = re.compile(
    r'(applytojob\.com|lever\.co|greenhouse\.io|job-boards\.greenhouse\.io|'
    r'boards\.greenhouse\.io|workday\.com|icims\.com|taleo\.net|smartrecruiters\.com|'
    r'bamboohr\.com|myworkdayjobs\.com|paylocity\.com|paycom\.com|ashbyhq\.com)',
    re.I,
)


def _find_job_links(html_text, base_url):
    """
    Find links that look like individual job pages.
    Includes same-domain links matching job URL patterns AND cross-domain
    links to known ATS platforms (e.g. applytojob.com, lever.co).
    Returns a deduplicated list of absolute URLs.
    """
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower()

    soup = BeautifulSoup(html_text, "lxml")
    seen = set()
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            continue

        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)
        link_domain = parsed.netloc.lower()

        text = a.get_text(strip=True)

        is_same_domain = link_domain == base_domain
        is_ats = bool(_ATS_DOMAINS.search(link_domain))
        has_job_path = bool(_JOB_URL_PATTERNS.search(parsed.path))
        has_job_text = 4 <= len(text) <= 100

        if is_same_domain and has_job_path and has_job_text:
            pass  # accept
        elif is_ats and has_job_text:
            pass  # accept cross-domain ATS link
        else:
            continue

        clean_url = abs_url.split("#")[0]
        if clean_url in seen or clean_url == base_url:
            continue
        seen.add(clean_url)
        links.append(clean_url)

    return links


def _extract_board_from_html(html_text, base_url):
    """Scan page for job links, fetch each, return list of raw job dicts."""
    job_links = _find_job_links(html_text, base_url)

    if not job_links:
        # Check if page appears JS-rendered
        soup = BeautifulSoup(html_text, "lxml")
        script_tags = soup.find_all("script", src=True)
        bundle_like = [s for s in script_tags if re.search(r'\.(chunk|bundle|main)\.[a-f0-9]+\.js', s.get("src", ""))]
        if bundle_like:
            print(
                "WARNING: Found 0 job links but page appears JavaScript-rendered "
                "(detected JS bundle script tags). Static scraping won't work here. "
                "Try pasting individual job URLs instead."
            )
            return []

        # Fallback: page may itself be a single job (e.g. /jobs path on a small org site)
        print(f"WARNING: Found 0 job links on {base_url}. Trying single-job extraction on this page.")
        return _extract_single_from_html(html_text, base_url)

    print(f"Found {len(job_links)} job links on board page.")
    results = []
    for i, link in enumerate(job_links):
        print(f"  [{i+1}/{len(job_links)}] Fetching: {link}")
        time.sleep(RATE_LIMIT_SLEEP)
        try:
            html = get_html(link)
            jobs = _extract_single_from_html(html, link)
            results.extend(jobs)
        except FetchError as e:
            print(f"  WARNING: Could not fetch {link}: {e}")

    return results


def _extract_single_from_html(html_text, url):
    """
    Try JSON-LD → OG tags → HTML heuristics.
    Returns list with 0 or 1 job dict.
    """
    soup = BeautifulSoup(html_text, "lxml")
    hostname = urlparse(url).netloc

    # 1. JSON-LD JobPosting
    job = _try_jsonld(soup, url, hostname)
    if job:
        return [job]

    # 2. OG tags
    job = _try_og_tags(soup, url, hostname)
    if job:
        return [job]

    # 3. HTML heuristics
    job = _try_html_heuristics(soup, url, hostname)
    if job:
        return [job]

    print(f"WARNING: Could not extract job from {url} — no usable fields found.")
    return []


def _try_jsonld(soup, url, hostname):
    """Extract job from JSON-LD <script type='application/ld+json'>."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle @graph wrapper
        if isinstance(data, dict) and data.get("@graph"):
            for item in data["@graph"]:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    data = item
                    break

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    data = item
                    break

        if not isinstance(data, dict) or data.get("@type") != "JobPosting":
            continue

        title = _clean(data.get("title") or data.get("name"))
        if not title:
            continue

        employer = _clean(
            _nested(data, "hiringOrganization", "name")
            or _nested(data, "hiringOrganization")
        )

        # Location: try structured address first, then plain string
        loc_obj = data.get("jobLocation") or {}
        if isinstance(loc_obj, list):
            loc_obj = loc_obj[0] if loc_obj else {}
        addr = loc_obj.get("address") or {}
        if isinstance(addr, str):
            location_raw = addr
        else:
            city = _clean(addr.get("addressLocality", ""))
            state = _clean(addr.get("addressRegion", ""))
            country = _clean(addr.get("addressCountry", ""))
            parts = [p for p in [city, state] if p]
            if not parts and country:
                parts = [country]
            location_raw = ", ".join(parts) if parts else None

        # Remote fallback
        if not location_raw:
            work_location = _clean(data.get("applicantLocationRequirements", ""))
            if work_location:
                location_raw = work_location
            elif str(data.get("jobLocationType", "")).upper() == "TELECOMMUTE":
                location_raw = "Remote"

        description = _clean_description(data.get("description", ""))
        salary_raw = _extract_jsonld_salary(data)
        posted_date = _clean(data.get("datePosted"))

        if title and location_raw:
            confidence = 1.0
        elif title:
            confidence = 0.7
            location_raw = location_raw or "Unknown"
        else:
            continue

        return {
            "title": title,
            "location_raw": location_raw or "Unknown",
            "source_url": url,
            "source_board": hostname,
            "employer": employer,
            "salary": salary_raw,
            "description": description,
            "posted_date": posted_date,
            "scraped_at": _now(),
            "confidence": confidence,
        }

    return None


def _try_og_tags(soup, url, hostname):
    """Fallback: extract from Open Graph meta tags."""
    og = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name") or ""
        content = _clean(meta.get("content", ""))
        if content:
            og[prop.lower()] = content

    title = og.get("og:title") or og.get("twitter:title")
    if not title:
        return None

    description = og.get("og:description") or og.get("twitter:description")
    employer = og.get("og:site_name")

    # Try OG description first; fall back to full page text for location
    location_raw = _extract_location_from_text(description or "")
    salary_raw = None
    if not location_raw:
        full_text = soup.get_text(" ", strip=True)
        location_raw = _extract_location_from_text(full_text)
        salary_raw = _extract_salary_from_text(full_text)
        if not description:
            description = _clean_description(full_text[:600])

    return {
        "title": title,
        "location_raw": location_raw or "Unknown",
        "source_url": url,
        "source_board": hostname,
        "employer": employer,
        "salary": salary_raw,
        "description": description,
        "posted_date": None,
        "scraped_at": _now(),
        "confidence": 0.55 if location_raw else 0.4,
    }


def _try_html_heuristics(soup, url, hostname):
    """Last-resort: grab <h1> as title, nearby text for location/salary."""
    # Title from <h1>
    h1 = soup.find("h1")
    title = _clean(h1.get_text(" ", strip=True)) if h1 else None
    if not title:
        return None

    full_text = soup.get_text(" ", strip=True)

    location_raw = _extract_location_from_text(full_text)
    salary_raw = _extract_salary_from_text(full_text)
    employer = _extract_employer_from_text(full_text)

    description = _clean_description(full_text[:600])

    confidence = 0.3 if location_raw else 0.15

    return {
        "title": title,
        "location_raw": location_raw or "Unknown",
        "source_url": url,
        "source_board": hostname,
        "employer": employer,
        "salary": salary_raw,
        "description": description,
        "posted_date": None,
        "scraped_at": _now(),
        "confidence": confidence,
    }


# ── helper functions ─────────────────────────────────────────────────────────

_CITY_STATE_RE = re.compile(
    r'\b([A-Z][a-z]{2,20}(?:\s[A-Z][a-z]{2,15})?),?\s+([A-Z]{2})\b'
)
_REMOTE_RE = re.compile(r'\b(remote|work from home|wfh|telecommute|virtual)\b', re.I)
_SALARY_RE = re.compile(r'\$[\d,]+(?:\.\d{2})?(?:\s*[-–]\s*\$[\d,]+(?:\.\d{2})?)?(?:\s*/\s*(?:hr|hour|year|yr|annual))?', re.I)
_EMPLOYER_LABELS = re.compile(r'(?:employer|organization|company|union|org)\s*:\s*([^\n\r.]{3,60})', re.I)


def _extract_location_from_text(text):
    if _REMOTE_RE.search(text):
        # If remote AND a city pattern, combine
        m = _CITY_STATE_RE.search(text)
        if m:
            return f"{m.group(1)}, {m.group(2)} / Remote"
        return "Remote"
    m = _CITY_STATE_RE.search(text)
    if m:
        return f"{m.group(1)}, {m.group(2)}"
    return None


def _extract_salary_from_text(text):
    m = _SALARY_RE.search(text)
    return m.group(0) if m else None


def _extract_employer_from_text(text):
    m = _EMPLOYER_LABELS.search(text)
    return _clean(m.group(1)) if m else None


def _extract_jsonld_salary(data):
    sal = data.get("baseSalary")
    if not sal:
        return None
    if isinstance(sal, str):
        return sal
    val = sal.get("value") or {}
    if isinstance(val, dict):
        min_val = val.get("minValue")
        max_val = val.get("maxValue")
        unit = _clean(val.get("unitText") or "")
        if min_val and max_val:
            return f"${min_val}–${max_val} {unit}".strip()
        if min_val:
            return f"${min_val} {unit}".strip()
        single = val.get("value")
        if single:
            return f"${single} {unit}".strip()
    return None


def _nested(d, *keys):
    """Safe nested dict access."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _clean(value):
    if not value:
        return None
    if not isinstance(value, str):
        return str(value)
    value = re.sub(r'\s+', ' ', value).strip()
    return value or None


def _clean_description(text):
    if not text:
        return None
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:600] or None


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
