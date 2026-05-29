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

# Structured block labels used by some listing formats (e.g. SEIU-USWW):
#   Location: X  Department: Y  Employment Type: Z  Minimum Experience: W  Compensation: $
# The entire block appears in a single <p>; prose follows Compensation value.
_STRUCT_LABEL_RE = re.compile(
    r'(Location|Department|Employment\s+Type|Minimum\s+Experience|Compensation)\s*:',
    re.IGNORECASE,
)
# Extended detection set covers AFSCME, UFCW, UPTE and other formats.
# A paragraph with >= 2 of these labels is treated as a structured-block paragraph
# and excluded from the prose description.
_STRUCT_DETECT_RE = re.compile(
    r'(?:Location|Department|Employment\s+Type|Minimum\s+Experience|Compensation|'
    r'Salary\s+Range|Salary|Starting\s+Salary|Position|Job\s+Title|Job\s+Classification|'
    r'Classification|Organization|Title|Reports\s+to|Approximate\s+Start\s+Date|'
    r'Benefits|COMPENSATION|Job\s+Category|Job\s+ID|Requisition|Deadline)\s*:',
    re.IGNORECASE,
)


def _strip_metadata_from_desc(text):
    """Strip a structured-metadata block from description text.

    Used in the reparse pass to clean legacy records that have structured
    labels (Location:, Department:, Salary Range:, etc.) in their descriptions.

    Finds the end of the last structured-label value (using the last dollar
    amount as a proxy) and returns the prose that follows.

    Returns (prose, True) if metadata was found and stripped,
    or (text, False) if no cleanable metadata was detected.
    """
    matches = list(_STRUCT_DETECT_RE.finditer(text))
    if not matches:
        return text, False

    # Find the last dollar amount anywhere in the text — prose almost always
    # follows the compensation figure.
    last_dollar_end = 0
    for m in re.finditer(
        r'\$[\d,]+(?:\.\d+)?(?:\s*(?:–|-|to)\s*\$[\d,]+(?:\.\d+)?)?'
        r'(?:\s+(?:per\s+\w+|annually|/\w+))?',
        text,
    ):
        last_dollar_end = m.end()

    if last_dollar_end:
        # Skip optional trailing context: "(Steps I–V...)", ", depending on..."
        tail = text[last_dollar_end:]
        skip_m = re.match(
            r'\s*(?:\([^)]{0,80}\))?(?:,\s+depending\s+[^.]+\.)?'
            r'(?:\s+plus\s+benefits[^.]*\.)?(?:\s+Benefits:[^.]*\.)?\s*',
            tail,
        )
        prose_start = last_dollar_end + (skip_m.end() if skip_m else 0)
        prose = text[prose_start:].strip()
        if prose and len(prose) > 40:
            return prose, True

    # No dollar amount — try to find prose start after the last label's value.
    # The value of a structured field is short (city, job type, etc.).
    last_m = matches[-1]
    tail = text[last_m.end():].strip()
    # Prose typically starts with an alphabetic word that is not itself a label value.
    # Heuristic: skip up to 80 chars of "label value", then look for prose.
    prose_m = re.match(r'.{0,80}?\s+(?=[A-Z][a-z]{4,})', tail, re.DOTALL)
    if prose_m:
        prose_start = last_m.end() + prose_m.end()
        prose = text[prose_start:].strip()
        if prose and len(prose) > 40:
            return prose, True

    return text, False


def _parse_structured_block(text):
    """Parse a SEIU/standard structured-block paragraph.

    Detects paragraphs that contain >= 2 structured-field labels and extracts:
      location, department, employment_type, experience, compensation, prose

    Returns None when fewer than 2 labels are found (not a structured block).
    """
    matches = list(_STRUCT_LABEL_RE.finditer(text))
    if len(matches) < 2:
        return None

    label_map = {
        'location': 'location',
        'department': 'department',
        'employment type': 'employment_type',
        'minimum experience': 'experience',
        'compensation': 'compensation',
    }

    fields = {v: None for v in label_map.values()}
    fields['prose'] = ''

    for i, m in enumerate(matches):
        raw_label = re.sub(r'\s+', ' ', m.group(1)).lower()
        key = label_map.get(raw_label)
        if key is None:
            continue
        value_start = m.end()
        value_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[value_start:value_end].strip()
        fields[key] = value or None

    # For the last label's value, separate the dollar amount from trailing prose.
    # Compensation is almost always last; the prose begins after the last $amount.
    last_m = matches[-1]
    last_raw = re.sub(r'\s+', ' ', last_m.group(1)).lower()
    last_key = label_map.get(last_raw)
    if last_key:
        tail = text[last_m.end():].strip()
        comp_val, prose = _split_value_and_prose(tail)
        fields[last_key] = comp_val or None
        fields['prose'] = prose

    return fields


def _split_value_and_prose(text):
    """Split 'Salary Range: $X – $Y About Organization...' into (value, prose).

    The value ends after the last dollar amount; the rest is prose.
    Falls back to returning (text, '') when no dollar sign is found.
    """
    dollar_end = 0
    for m in re.finditer(
        r'(?:(?:Hourly Rate|Salary Range|Annual Salary)\s*:\s*)?'
        r'\$[\d,]+(?:\.\d+)?(?:\s*(?:–|-|to)\s*\$[\d,]+(?:\.\d+)?)?'
        r'(?:\s+per\s+\w+)?',
        text,
    ):
        dollar_end = m.end()

    if dollar_end:
        return text[:dollar_end].strip(), text[dollar_end:].strip()
    return text.strip(), ''

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
      <p> tags = description body, optional structured-block paragraph, apply URL line

    Some listings (e.g. SEIU-USWW) embed a structured block in a single <p>:
      Location: X  Department: Y  Employment Type: Z  Minimum Experience: W  Compensation: $
    That block is parsed into separate fields; the trailing prose becomes the description.
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
        loc_text = re.sub(r'\s*\(.*?\)\s*$', '', loc_text).strip()
        location_raw = loc_text if loc_text else None

    # Structured-block fields (populated when a structured-block paragraph is found)
    department = None
    employment_type = None
    experience_raw = None
    salary_raw = None

    # Scan paragraphs: detect structured-block paragraphs, collect prose description
    desc_parts = []

    for p in paragraphs:
        txt = p.get_text(" ", strip=True)
        txt = re.sub(r'\s+', ' ', txt).strip()
        if not txt:
            continue

        # Skip apply / equal-opportunity boilerplate
        if re.match(r'(Apply\b|WHEN APPLYING|Equal Opportunity)', txt, re.I):
            continue

        # Detect structured-block paragraph (>= 2 structured labels present)
        struct_label_count = len(_STRUCT_DETECT_RE.findall(txt))
        if struct_label_count >= 2:
            # Try the full SEIU-style parser first
            parsed = _parse_structured_block(txt)
            if parsed:
                if parsed.get('location'):
                    location_raw = parsed['location']  # overrides h4 location
                department = parsed.get('department')
                employment_type = parsed.get('employment_type')
                experience_raw = parsed.get('experience')
                if parsed.get('compensation'):
                    salary_raw = parsed['compensation']
                # Add the non-structured prose remainder to description
                if parsed.get('prose'):
                    desc_parts.append(parsed['prose'])
            else:
                # >= 2 labels but parser didn't extract (unusual format) — skip from desc
                pass
            continue

        # Regular prose paragraph
        desc_parts.append(txt)

    # Salary fallback: if no Compensation: label was found, look for the first <p> with $
    # (prose-only listings that mention salary inline)
    if not salary_raw:
        for p in paragraphs:
            txt = re.sub(r'\s+', ' ', p.get_text(" ", strip=True)).strip()
            if re.search(r'\$\s*[\d,]+', txt):
                if re.match(r'(Apply|WHEN APPLYING)', txt, re.I):
                    continue
                salary_raw = txt[:300]
                break
        if not salary_raw:
            for p in paragraphs:
                txt = re.sub(r'\s+', ' ', p.get_text(" ", strip=True)).strip()
                if re.match(r'(salary|compensation|pay range|wage|starting pay)', txt, re.I):
                    salary_raw = txt[:300]
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
            url_match = re.search(r'https?://\S+', txt)
            if url_match:
                apply_url = url_match.group(0).rstrip(".")
                break
    if apply_url == url:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "unionjobs.com" not in href and "mailto:" not in href:
                apply_url = href
                break

    description = " ".join(desc_parts)
    description = re.sub(r'\s+', ' ', description).strip()[:2000]

    # date_posted: not present on unionjobs.com listing pages
    date_posted = None

    return {
        "job_id": job_id,
        "title": title,
        "organization": organization,
        "location_raw": location_raw,
        "state_abbr": parse_state_abbr(location_raw),
        "date_posted": date_posted,
        "salary_raw": salary_raw,
        "department": department,
        "employment_type": employment_type,
        "experience_raw": experience_raw,
        "description": description,
        "apply_url": apply_url,
        "source": "unionjobs.com",
    }


def reparse_existing(output_json=OUTPUT_JSON):
    """Re-parse structured blocks from an existing unionjobs_raw.json without scraping.

    Two-pass approach:
      1. Full SEIU-style structured-block parser (extracts all labeled fields).
      2. Fallback: broad metadata-stripper that removes any paragraph whose description
         starts with structured labels, using the last dollar amount as the prose boundary.
    """
    import os
    if not os.path.exists(output_json):
        print(f"ERROR: {output_json} not found. Run the scraper first.")
        return

    with open(output_json, encoding="utf-8") as f:
        records = json.load(f)

    def _norm(s):
        """Normalize non-breaking spaces and collapse whitespace."""
        return re.sub(r'\s+', ' ', s.replace('\xa0', ' ')).strip()

    cleaned = 0
    for rec in records:
        # Legacy records may have 'salary' instead of 'salary_raw'.
        raw_salary = _norm(rec.get("salary") or rec.get("salary_raw") or "")
        raw_desc = _norm(rec.get("description") or "")

        # Always rename 'salary' → 'salary_raw'
        if 'salary' in rec:
            rec['salary_raw'] = rec.pop('salary')

        # --- Pass 1: Full SEIU-style parser ---
        # Candidate for structured-block parsing is the salary field (captured from the
        # first <p> with $, which is usually the structured-block paragraph).
        candidate = raw_salary or raw_desc
        struct_count_in_cand = len(_STRUCT_DETECT_RE.findall(candidate))

        if struct_count_in_cand >= 2:
            parsed = _parse_structured_block(candidate)
            if parsed:
                if parsed.get('location'):
                    rec['location_raw'] = parsed['location']
                    rec['state_abbr'] = parse_state_abbr(parsed['location'])
                rec['department'] = parsed.get('department')
                rec['employment_type'] = parsed.get('employment_type')
                rec['experience_raw'] = parsed.get('experience')
                if parsed.get('compensation'):
                    rec['salary_raw'] = parsed['compensation']

                # Remove the structured block from description.
                # prose is the text AFTER the block in candidate.
                prose = parsed.get('prose') or ''
                block_text = candidate[: len(candidate) - len(prose)].strip()
                clean_desc = raw_desc
                if block_text and clean_desc.startswith(block_text):
                    clean_desc = clean_desc[len(block_text):].strip()
                elif prose and prose in clean_desc:
                    clean_desc = clean_desc[clean_desc.index(prose):]

                rec['description'] = clean_desc[:2000]
                cleaned += 1
                continue

        # --- Pass 2: Broad metadata stripper for remaining contamination ---
        struct_labels = ['Location:', 'Department:']
        desc_contaminated = any(lbl in raw_desc for lbl in struct_labels)
        if desc_contaminated:
            prose, stripped = _strip_metadata_from_desc(raw_desc)
            if stripped:
                rec['description'] = prose[:2000]
                if not rec.get('salary_raw') and raw_salary:
                    _, stripped_sal = _strip_metadata_from_desc(raw_salary)
                    if not stripped_sal:
                        rec['salary_raw'] = raw_salary[:300]
                cleaned += 1

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"Reparsed {len(records)} records. Cleaned: {cleaned}.")
    print(f"Output written to {output_json}")

    struct_patterns = ['Location:', 'Department:']
    still_contaminated = [
        r['job_id'] for r in records
        if any(p in (r.get('description') or '') for p in struct_patterns)
    ]
    # --- Pass 3: Surgical label removal for records that still have Location:/Department: ---
    # Handles edge cases: label embedded mid-prose, label at end near truncation boundary,
    # and descriptions that start with a short metadata preamble with no dollar amounts.
    _INLINE_LABEL_RE = re.compile(
        r'\s*(?:Location|Department)\s*:\s*[^.]{1,120}?(?=\s+[A-Z]|\s*$|\.\s)',
        re.IGNORECASE,
    )
    pass3_cleaned = 0
    for rec in records:
        desc = rec.get('description') or ''
        if not ('Location:' in desc or 'Department:' in desc):
            continue
        # Try to find "Who We Are:" or "DESCRIPTION:" or "About " as a prose marker
        # (for records that start with metadata before the prose marker)
        for prose_marker in [r'\bWho\s+We\s+Are\b', r'\bDESCRIPTION\b', r'\bAbout\s+', r'\bPosition\s+Description\b']:
            m = re.search(prose_marker, desc, re.IGNORECASE)
            if m and m.start() > 0:
                prose_candidate = desc[m.start():]
                if 'Location:' not in prose_candidate and 'Department:' not in prose_candidate:
                    rec['description'] = prose_candidate[:2000]
                    pass3_cleaned += 1
                    break
        else:
            # No prose marker found — try surgical removal of inline Location:/Department: labels
            # Only remove "Location: [value]" when the value is short (≤80 chars to next sentence)
            new_desc = _INLINE_LABEL_RE.sub(' ', desc).strip()
            new_desc = re.sub(r'\s{2,}', ' ', new_desc)
            if 'Location:' not in new_desc and 'Department:' not in new_desc and len(new_desc) > 40:
                rec['description'] = new_desc[:2000]
                pass3_cleaned += 1

    if pass3_cleaned:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print(f"Pass 3 cleaned {pass3_cleaned} additional records.")

    struct_patterns = ['Location:', 'Department:']
    still_contaminated = [
        r['job_id'] for r in records
        if any(p in (r.get('description') or '') for p in struct_patterns)
    ]
    if still_contaminated:
        print(f"NOTE: {len(still_contaminated)} records retain Location:/Department: (embedded in prose or too complex to clean retroactively).")
        for jid in still_contaminated[:5]:
            desc = next((r.get('description','') for r in records if r['job_id'] == jid), '')
            print(f"  {jid}: {desc[:120]}")
    else:
        print("All descriptions clean of structured field labels.")


def main():
    import os
    import sys

    # --reparse: clean existing output/unionjobs_raw.json without live scraping
    if "--reparse" in sys.argv:
        os.makedirs("output", exist_ok=True)
        reparse_existing()
        return

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
