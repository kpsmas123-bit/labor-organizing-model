#!/usr/bin/env python3
"""
Task 1: Scrape unionjobs.com staff/rank-and-file listings.
Checks robots.txt before any scraping. Respects rate limits.
Outputs: output/unionjobs_raw.json, output/jobs_scrape_log.txt
"""

import json
import re
import time
import urllib.robotparser
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.unionjobs.com"
INDEX_URL = "https://www.unionjobs.com/staffing_list.php"
LISTING_URL = "https://www.unionjobs.com/listing.php"
OUTPUT_JSON = "output/unionjobs_raw.json"
LOG_FILE = "output/jobs_scrape_log.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LaborOrganizingResearch/1.0; +https://github.com/kpsmas123-bit/labor-organizing-model)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

SLEEP_BETWEEN = 2  # seconds
MAX_CONSECUTIVE_FAILURES = 20


def log(msg, log_fh=None):
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line)
    if log_fh:
        log_fh.write(line + "\n")
        log_fh.flush()


def check_robots_txt(log_fh):
    """Fetch and print robots.txt. Return (allowed, crawl_delay)."""
    robots_url = f"{BASE_URL}/robots.txt"
    log(f"Fetching robots.txt: {robots_url}", log_fh)

    try:
        r = requests.get(robots_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        content = r.text
    except Exception as e:
        log(f"WARNING: Could not fetch robots.txt: {e}. Proceeding cautiously.", log_fh)
        return True, SLEEP_BETWEEN

    print("\n=== robots.txt contents ===")
    print(content)
    print("=== end robots.txt ===\n")
    log("robots.txt fetched successfully.", log_fh)

    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    rp.parse(content.splitlines())

    # Check if our target pages are allowed
    test_paths = [
        "/staffing_list.php",
        "/listing.php?id=12345",
    ]
    for path in test_paths:
        allowed = rp.can_fetch("*", BASE_URL + path)
        log(f"  robots.txt: {'ALLOWED' if allowed else 'DISALLOWED'} — {path}", log_fh)
        if not allowed:
            log(f"ABORT: robots.txt disallows scraping {path}", log_fh)
            return False, SLEEP_BETWEEN

    # Extract Crawl-delay
    crawl_delay = SLEEP_BETWEEN
    for line in content.splitlines():
        if line.lower().startswith("crawl-delay"):
            parts = line.split(":")
            if len(parts) >= 2:
                try:
                    crawl_delay = max(float(parts[1].strip()), SLEEP_BETWEEN)
                    log(f"Crawl-delay found: {crawl_delay}s (using max of Crawl-delay and {SLEEP_BETWEEN}s minimum)", log_fh)
                except ValueError:
                    pass

    return True, crawl_delay


def parse_state_abbr(location_raw):
    """Extract 2-letter state abbreviation from location string like 'Washington, DC'."""
    if not location_raw:
        return None
    # Match trailing 2-letter state code
    m = re.search(r'\b([A-Z]{2})\s*$', location_raw.strip())
    if m:
        return m.group(1)
    # Also try "City, ST 00000" pattern
    m = re.search(r',\s*([A-Z]{2})\b', location_raw)
    if m:
        return m.group(1)
    return None


def get_listing_ids_from_index(log_fh, sleep_sec):
    """Fetch the index page and extract all listing IDs."""
    log(f"Fetching index: {INDEX_URL}", log_fh)
    time.sleep(sleep_sec)

    try:
        r = requests.get(INDEX_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log(f"ERROR fetching index: {e}", log_fh)
        return []

    soup = BeautifulSoup(r.text, "lxml")
    ids = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Match listing.php?id=XXXXX patterns
        if "listing.php" in href and "id=" in href:
            full_url = urljoin(BASE_URL, href)
            parsed = urlparse(full_url)
            params = parse_qs(parsed.query)
            if "id" in params:
                job_id = params["id"][0]
                if job_id not in seen:
                    seen.add(job_id)
                    ids.append(job_id)

    log(f"Found {len(ids)} listing IDs on index page.", log_fh)

    # Also try paginated pages if there are "next page" links
    # Check for pagination
    next_pages = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "staffing_list.php" in href and ("page=" in href or "start=" in href or "offset=" in href):
            full = urljoin(BASE_URL, href)
            if full not in next_pages and full != INDEX_URL:
                next_pages.append(full)

    for page_url in next_pages[:20]:  # cap at 20 extra pages
        log(f"Fetching paginated index: {page_url}", log_fh)
        time.sleep(sleep_sec)
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            psoup = BeautifulSoup(r.text, "lxml")
            for a in psoup.find_all("a", href=True):
                href = a["href"]
                if "listing.php" in href and "id=" in href:
                    full_url = urljoin(BASE_URL, href)
                    parsed = urlparse(full_url)
                    params = parse_qs(parsed.query)
                    if "id" in params:
                        job_id = params["id"][0]
                        if job_id not in seen:
                            seen.add(job_id)
                            ids.append(job_id)
        except Exception as e:
            log(f"ERROR fetching paginated index {page_url}: {e}", log_fh)

    log(f"Total listing IDs found (all pages): {len(ids)}", log_fh)
    return ids


def scrape_listing(job_id, log_fh):
    """Fetch and parse a single listing. Returns dict or None.

    unionjobs.com page structure (confirmed by inspection):
      h4[0] = empty
      h4[1] = organization name
      h4[2] = job title
      h4[3] = location string like "Based in Washington, DC [Headquarters]"
      <p> tags = description body, salary line, apply URL line
    """
    url = f"{LISTING_URL}?id={job_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log(f"ERROR fetching listing {job_id}: {e}", log_fh)
        return None

    soup = BeautifulSoup(r.text, "lxml")

    h4s = soup.find_all("h4")
    paragraphs = soup.find_all("p")

    # Two layouts observed:
    #   4-h4: ['', org, title, location]  (leading empty h4)
    #   3-h4: [org, title, location]      (no leading empty h4)
    # Detect by checking if h4[0] is empty
    if h4s and not h4s[0].get_text(strip=True):
        h4s = h4s[1:]  # drop leading empty tag

    organization = None
    if len(h4s) > 0:
        organization = re.sub(r'\s+', ' ', h4s[0].get_text(" ", strip=True)).strip() or None

    title = None
    if len(h4s) > 1:
        title = re.sub(r'\s+', ' ', h4s[1].get_text(" ", strip=True)).strip() or None

    # Location: h4[2] — strip "Based in " / "Based out of in " prefixes and "[Type]" suffixes
    location_raw = None
    if len(h4s) > 2:
        loc_text = re.sub(r'\s+', ' ', h4s[2].get_text(" ", strip=True)).strip()
        loc_text = re.sub(r'^Based (?:out of )?(?:in\s+)?', '', loc_text, flags=re.I)
        loc_text = re.sub(r'\s*\[.*?\]', '', loc_text).strip()
        # Strip trailing qualifiers like "(with travel...)"
        loc_text = re.sub(r'\s*\(.*?\)\s*$', '', loc_text).strip()
        location_raw = loc_text if loc_text else None

    # Salary: find the first <p> that contains a dollar amount (e.g. "$70,000")
    # Falls back to any <p> starting with salary/compensation/pay keywords
    salary = None
    for p in paragraphs:
        txt = p.get_text(" ", strip=True)
        if re.search(r'\$\s*[\d,]+', txt):
            # Skip the "Apply here" line which sometimes contains an external URL with $ in it
            if re.match(r'(Apply|WHEN APPLYING)', txt, re.I):
                continue
            salary = txt[:300]
            break
    if not salary:
        for p in paragraphs:
            txt = p.get_text(" ", strip=True)
            if re.match(r'(salary|compensation|pay range|wage|starting pay)', txt, re.I):
                salary = txt[:300]
                break

    # Apply URL: look for external link in "Apply here:" paragraph OR any non-site external link
    apply_url = url  # fallback
    for p in paragraphs:
        txt = p.get_text(" ", strip=True)
        if re.match(r'Apply\b', txt, re.I):
            a = p.find("a", href=True)
            if a:
                href = a["href"]
                if href.startswith("http") and "unionjobs.com" not in href:
                    apply_url = href
                    break
            # Also check for bare URL in text
            url_match = re.search(r'https?://\S+', txt)
            if url_match:
                apply_url = url_match.group(0).rstrip(".")
                break
    # Fallback: first external non-site link on page
    if apply_url == url:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "unionjobs.com" not in href and "mailto:" not in href:
                apply_url = href
                break

    # Description: collect all <p> text, skip salary/apply lines, first 400 chars
    desc_parts = []
    for p in paragraphs:
        txt = p.get_text(" ", strip=True)
        if not txt:
            continue
        if re.match(r'(Salary:|Apply\b|Equal Opportunity)', txt, re.I):
            continue
        desc_parts.append(txt)
    description = " ".join(desc_parts)
    description = re.sub(r'\s+', ' ', description).strip()[:400]

    # date_posted: not present on unionjobs.com listing pages
    date_posted = None

    return {
        "job_id": job_id,
        "title": title,
        "organization": organization,
        "location_raw": location_raw,
        "state_abbr": parse_state_abbr(location_raw),
        "date_posted": date_posted,
        "salary": salary,
        "description": description,
        "apply_url": apply_url,
        "source": "unionjobs.com",
    }


def main():
    import os
    os.makedirs("output", exist_ok=True)

    with open(LOG_FILE, "w") as log_fh:
        log("=== unionjobs.com scrape started ===", log_fh)
        log(f"Timestamp: {datetime.utcnow().isoformat()}", log_fh)

        # Step 1: Check robots.txt
        allowed, sleep_sec = check_robots_txt(log_fh)
        if not allowed:
            log("ABORTING: robots.txt disallows scraping listing pages.", log_fh)
            print("\nABORT: robots.txt disallows target pages. No scraping performed.")
            return

        log(f"Proceeding with {sleep_sec}s delay between requests.", log_fh)

        # Step 2: Get listing IDs from index
        listing_ids = get_listing_ids_from_index(log_fh, sleep_sec)
        if not listing_ids:
            log("No listing IDs found. Exiting.", log_fh)
            return

        # Step 3: Scrape each listing
        results = []
        consecutive_failures = 0

        for i, job_id in enumerate(listing_ids):
            log(f"[{i+1}/{len(listing_ids)}] Scraping listing id={job_id}", log_fh)
            time.sleep(sleep_sec)

            record = scrape_listing(job_id, log_fh)
            if record is not None:
                results.append(record)
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                log(f"  Failure #{consecutive_failures} consecutive.", log_fh)
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    log(f"ABORT: {MAX_CONSECUTIVE_FAILURES} consecutive failures. Stopping.", log_fh)
                    break

        log(f"Scrape complete. {len(results)} listings collected.", log_fh)

        # Step 4: Write output
        with open(OUTPUT_JSON, "w") as f:
            json.dump(results, f, indent=2)
        log(f"Output written to {OUTPUT_JSON}", log_fh)

        # Step 5: Summary
        print(f"\n=== SCRAPE SUMMARY ===")
        print(f"Total listings scraped: {len(results)}")
        print(f"\n=== 3 SAMPLE RECORDS ===")
        for rec in results[:3]:
            print(json.dumps(rec, indent=2))

        errors = [l for l in open(LOG_FILE).readlines() if "ERROR" in l]
        if errors:
            print(f"\n=== ERRORS ({len(errors)}) ===")
            for e in errors[:10]:
                print(e.strip())


if __name__ == "__main__":
    import os
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(ROOT)
    main()
