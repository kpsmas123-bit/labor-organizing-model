"""
Terrain v2.0 — Congress.gov + House Clerk Roll-Call Vote Ingestion

Fetches roll-call vote records for defined key votes using two sources:

  1. Congress.gov API v3 (118th Congress+, beta)
     Endpoint: GET /v3/house-vote/{congress}/{session}/{roll_call}/members
     Key required: CONGRESS_API_KEY in .env

  2. House Clerk XML (117th Congress and earlier)
     URL: https://clerk.house.gov/evs/{year}/roll{NNN:03d}.xml
     No key required.

Senate votes: senate.gov XML
  URL: https://www.senate.gov/legislative/LIS/roll_call_votes/
       vote{congress}{session}/vote_{congress}_{session}_{vote_number:05d}.xml
  No key required.

Output:
  data/processed/federal_key_votes.csv       — one row per member per vote
  data/processed/federal_key_vote_scores.csv — one row per member, aggregated

Usage:
  python scripts/ingest_congress_votes.py

Reads:  config/key_votes.json
Writes: data/processed/federal_key_votes.csv
        data/processed/federal_key_vote_scores.csv
"""

import csv
import json
import logging
import os
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "key_votes.json"
OUTPUT_DIR = REPO_ROOT / "data" / "processed"
VOTES_CSV = OUTPUT_DIR / "federal_key_votes.csv"
SCORES_CSV = OUTPUT_DIR / "federal_key_vote_scores.csv"

CONGRESS_API_BASE = "https://api.congress.gov/v3"
HOUSE_CLERK_XML_BASE = "https://clerk.house.gov/evs"
SENATE_XML_BASE = "https://www.senate.gov/legislative/LIS/roll_call_votes"
RATE_LIMIT_DELAY = 0.5  # seconds between API requests

VOTE_CSV_FIELDS = [
    "member_id", "member_name", "state", "party", "chamber", "district",
    "vote_id", "vote_name", "congress", "vote_position", "is_pro_labor",
    "is_not_voting",
]

SCORE_CSV_FIELDS = [
    "member_id", "member_name", "state", "party", "chamber", "district",
    "votes_cast", "pro_labor_votes", "key_vote_score",
]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def get_congress_api_key() -> str:
    key = os.environ.get("CONGRESS_API_KEY", "").strip()
    if not key:
        log.error(
            "CONGRESS_API_KEY not found in environment. "
            "Register at https://api.congress.gov/sign-up/ "
            "and add CONGRESS_API_KEY=your_key to .env"
        )
        sys.exit(1)
    return key


def congress_api_get(path: str, api_key: str, params: Optional[dict] = None) -> Optional[dict]:
    """GET a Congress.gov API v3 endpoint. Returns parsed JSON or None on error."""
    url = f"{CONGRESS_API_BASE}/{path}"
    query = {"api_key": api_key, "format": "json", "limit": 250}
    if params:
        query.update(params)
    try:
        resp = requests.get(url, params=query, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        log.warning("HTTP %s for %s: %s", resp.status_code, url, e)
        return None
    except requests.RequestException as e:
        log.warning("Request error for %s: %s", url, e)
        return None


def fetch_house_clerk_xml(year: int, roll_call: int) -> Optional[ET.Element]:
    """
    Fetch House Clerk roll-call XML for a pre-118th-Congress vote.
    URL: https://clerk.house.gov/evs/{year}/roll{NNN:03d}.xml
    Returns the root XML element, or None on error.
    """
    url = f"{HOUSE_CLERK_XML_BASE}/{year}/roll{roll_call:03d}.xml"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TerrainDataPipeline/2.0; research use)",
        "Accept": "application/xml, text/xml, */*",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return ET.fromstring(resp.text)
    except requests.HTTPError as e:
        log.warning("HTTP %s fetching House Clerk XML %s: %s", resp.status_code, url, e)
        return None
    except requests.RequestException as e:
        log.warning("Request error fetching House Clerk XML %s: %s", url, e)
        return None
    except ET.ParseError as e:
        log.warning("XML parse error for %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Data extraction — Senate.gov XML
# ---------------------------------------------------------------------------

def fetch_senate_xml(congress: int, session: int, roll_call: int) -> Optional[ET.Element]:
    """
    Fetch Senate roll-call XML from senate.gov.
    URL: /vote{congress}{session}/vote_{congress}_{session}_{roll_call:05d}.xml
    No API key required.
    """
    url = (
        f"{SENATE_XML_BASE}/vote{congress}{session}/"
        f"vote_{congress}_{session}_{roll_call:05d}.xml"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TerrainDataPipeline/2.0; research use)",
        "Accept": "application/xml, text/xml, */*",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return ET.fromstring(resp.text)
    except requests.HTTPError as e:
        log.warning("HTTP %s fetching Senate XML %s: %s", resp.status_code, url, e)
        return None
    except requests.RequestException as e:
        log.warning("Request error fetching Senate XML %s: %s", url, e)
        return None
    except ET.ParseError as e:
        log.warning("XML parse error for %s: %s", url, e)
        return None


def parse_senate_xml(root: ET.Element) -> list[dict]:
    """
    Parse Senate roll-call XML into per-member vote records.

    XML structure:
      <roll_call_vote>
        <members>
          <member>
            <lis_member_id>S313</lis_member_id>
            <last_name>Sanders</last_name>
            <first_name>Bernard</first_name>
            <party>I</party>
            <state>VT</state>
            <vote_cast>Yea</vote_cast>
          </member>
          ...
        </members>
      </roll_call_vote>

    Normalizes Yea→yes, Nay→no for consistency with House records.
    """
    results = []
    members = root.find("members")
    if members is None:
        log.warning("No <members> element in Senate XML")
        return []

    position_map = {"yea": "yes", "nay": "no", "not voting": "not voting", "present": "present"}

    for member in members.findall("member"):
        raw_position = (member.findtext("vote_cast") or "").strip().lower()
        position = position_map.get(raw_position, raw_position)

        last = (member.findtext("last_name") or "").strip()
        first = (member.findtext("first_name") or "").strip()
        member_name = f"{first} {last}".strip() if first else last

        results.append({
            "member_id": (member.findtext("lis_member_id") or "").strip(),
            "member_name": member_name,
            "state": (member.findtext("state") or "").strip(),
            "party": (member.findtext("party") or "").strip(),
            "district": "",  # Senate has no districts
            "vote_position": position,
        })

    return results


# ---------------------------------------------------------------------------
# Data extraction — Congress.gov API (118th Congress+)
# ---------------------------------------------------------------------------

def fetch_congress_gov_members(congress: int, session: int, roll_call: int, api_key: str) -> list[dict]:
    """
    Fetch per-member votes from Congress.gov API v3 house-vote endpoint.
    Available for 118th Congress onward.

    Returns a list of member vote dicts with keys:
      bioguide_id, member_name, state, party, district, vote_position
    """
    path = f"house-vote/{congress}/{session}/{roll_call}/members"
    data = congress_api_get(path, api_key)
    time.sleep(RATE_LIMIT_DELAY)

    if not data:
        return []

    # Response structure: {"houseRollCallVote": {"members": [...]}}
    vote_data = data.get("houseRollCallVote", {})
    members = vote_data.get("members", [])

    if not members:
        log.warning("No member records in Congress.gov response for %d/%d/%d", congress, session, roll_call)
        return []

    results = []
    for m in members:
        member_info = m.get("member", {})
        results.append({
            "member_id": member_info.get("bioguideId", ""),
            "member_name": f"{member_info.get('firstName', '')} {member_info.get('lastName', '')}".strip(),
            "state": member_info.get("stateCode", ""),
            "party": member_info.get("partyCode", member_info.get("partyName", "")),
            "district": member_info.get("district", ""),
            "vote_position": m.get("votePosition", "").strip().lower(),
        })
    return results


# ---------------------------------------------------------------------------
# Data extraction — House Clerk XML (pre-118th Congress)
# ---------------------------------------------------------------------------

def parse_house_clerk_xml(root: ET.Element) -> list[dict]:
    """
    Parse the House Clerk roll-call XML into per-member vote records.

    Expected XML structure:
      <rollcall-vote>
        <vote-metadata>...</vote-metadata>
        <vote-data>
          <recorded-vote>
            <legislator name-id="..." party="D" state="NY" district="14">Name</legislator>
            <vote>Yea</vote>
          </recorded-vote>
          ...
        </vote-data>
      </rollcall-vote>
    """
    results = []
    vote_data = root.find("vote-data")
    if vote_data is None:
        log.warning("No <vote-data> element in House Clerk XML")
        return []

    for recorded in vote_data.findall("recorded-vote"):
        legislator = recorded.find("legislator")
        vote_elem = recorded.find("vote")
        if legislator is None or vote_elem is None:
            continue

        member_name = (legislator.text or "").strip()
        raw_position = (vote_elem.text or "").strip().lower()

        # Normalize position: "yea" → "yes", "nay" → "no"
        position_map = {"yea": "yes", "nay": "no", "aye": "yes"}
        position = position_map.get(raw_position, raw_position)

        results.append({
            "member_id": legislator.get("name-id", ""),
            "member_name": member_name,
            "state": legislator.get("state", ""),
            "party": legislator.get("party", ""),
            "district": legislator.get("district", ""),
            "vote_position": position,
        })

    return results


# ---------------------------------------------------------------------------
# Vote processing dispatcher
# ---------------------------------------------------------------------------

def process_vote_config(vote_cfg: dict, api_key: str) -> list[dict]:
    """
    Fetch and process a single vote from config/key_votes.json.
    Returns per-member records matching VOTE_CSV_FIELDS.
    Skips gracefully for votes with floor_vote=False or missing roll call data.
    """
    vote_id = vote_cfg["id"]
    vote_name = vote_cfg["name"]
    congress = vote_cfg["congress"]
    chamber = vote_cfg["chamber"]
    pro_labor_position = vote_cfg.get("pro_labor_vote", "yes").lower()

    # Skip votes with no floor record
    if vote_cfg.get("floor_vote") is False:
        skip_reason = vote_cfg.get("skip_reason", "no floor vote")
        log.warning("SKIP %s — %s", vote_id, skip_reason[:120])
        return []

    # Skip pending Sam decisions
    if vote_cfg.get("floor_vote") == "pending_verification":
        log.warning("SKIP %s — pending Sam decision on vote source", vote_id)
        return []

    # Skip committee-only votes
    if vote_cfg.get("vote_type") == "committee":
        log.warning("SKIP %s — committee vote only", vote_id)
        return []

    roll_call = vote_cfg.get("roll_call_number")
    if not roll_call:
        log.warning("SKIP %s — no roll_call_number in config", vote_id)
        return []

    data_source = vote_cfg.get("data_source")
    year = vote_cfg.get("year")

    if data_source == "house_clerk_xml":
        if not year:
            log.warning("SKIP %s — data_source is house_clerk_xml but no year", vote_id)
            return []
        log.info("Fetching %s — House Clerk XML %d/roll%03d", vote_id, year, roll_call)
        root = fetch_house_clerk_xml(year, roll_call)
        if root is None:
            log.warning("SKIP %s — could not fetch House Clerk XML", vote_id)
            return []
        raw_members = parse_house_clerk_xml(root)

    elif data_source == "senate_gov_xml":
        session = vote_cfg.get("session", 1)
        log.info("Fetching %s — Senate.gov XML %d/%d/%d", vote_id, congress, session, roll_call)
        root = fetch_senate_xml(congress, session, roll_call)
        if root is None:
            log.warning("SKIP %s — could not fetch Senate.gov XML", vote_id)
            return []
        raw_members = parse_senate_xml(root)
        time.sleep(RATE_LIMIT_DELAY)

    elif data_source == "congress_gov_api":
        session = vote_cfg.get("session", 1)
        log.info("Fetching %s — Congress.gov API %d/%d/%d", vote_id, congress, session, roll_call)
        raw_members = fetch_congress_gov_members(congress, session, roll_call, api_key)

    else:
        log.warning("SKIP %s — unknown or missing data_source '%s'", vote_id, data_source)
        return []

    if not raw_members:
        log.warning("SKIP %s — no member records returned", vote_id)
        return []

    records = []
    for m in raw_members:
        position = m["vote_position"]
        is_not_voting = position in ("not voting", "present", "")
        is_pro_labor = (not is_not_voting) and (position == pro_labor_position)

        records.append({
            "member_id": m["member_id"],
            "member_name": m["member_name"],
            "state": m["state"],
            "party": m["party"],
            "chamber": chamber,
            "district": m["district"],
            "vote_id": vote_id,
            "vote_name": vote_name,
            "congress": congress,
            "vote_position": position,
            "is_pro_labor": is_pro_labor,
            "is_not_voting": is_not_voting,
        })

    log.info("  %s — %d member records", vote_id, len(records))
    return records


# ---------------------------------------------------------------------------
# Score aggregation
# ---------------------------------------------------------------------------

def compute_scores(all_records: list[dict]) -> list[dict]:
    """
    Aggregate per-member alignment scores across all votes.

    key_vote_score = pro_labor_votes / votes_cast
    Members who were not voting on every tracked vote get score=None.
    """
    member_meta: dict[str, dict] = {}
    member_rows: dict[str, list[dict]] = defaultdict(list)

    for r in all_records:
        mid = r["member_id"]
        member_meta[mid] = {k: r[k] for k in ("member_name", "state", "party", "chamber", "district")}
        member_rows[mid].append(r)

    scores = []
    for mid, rows in member_rows.items():
        votes_cast = sum(1 for r in rows if not r["is_not_voting"])
        pro_labor = sum(1 for r in rows if r["is_pro_labor"])
        score = round(pro_labor / votes_cast, 4) if votes_cast > 0 else None

        scores.append({
            "member_id": mid,
            **member_meta[mid],
            "votes_cast": votes_cast,
            "pro_labor_votes": pro_labor,
            "key_vote_score": score,
        })

    return sorted(scores, key=lambda x: (x["state"], x["member_name"]))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    log.info("Wrote %d rows → %s", len(rows), path)


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------

def print_validation_report(scores: list[dict], all_records: list[dict]) -> None:
    scored = [s for s in scores if s["key_vote_score"] is not None]
    n_scored = len(scored)
    n_full = sum(1 for s in scored if s["key_vote_score"] == 1.0)
    n_zero = sum(1 for s in scored if s["key_vote_score"] == 0.0)
    median_score = sorted(s["key_vote_score"] for s in scored)[n_scored // 2] if scored else None

    vote_ids = sorted({r["vote_id"] for r in all_records})

    print("\n=== VALIDATION REPORT ===")
    print(f"Unique members with vote records: {len(scores)}")
    print(f"Members with ≥1 cast vote (scored): {n_scored}")
    print(f"Score distribution:")
    print(f"  1.0 (all pro-labor): {n_full}")
    print(f"  0.0 (none pro-labor): {n_zero}")
    print(f"  Median: {median_score}")
    print("\nVotes processed:")
    for vid in vote_ids:
        n = sum(1 for r in all_records if r["vote_id"] == vid)
        print(f"  {vid}: {n} member records")

    print("\n=== SPOT CHECKS ===")
    spot_names = ["Ocasio-Cortez", "Pelosi", "Manchin", "McCarthy", "McConnell"]
    for name in spot_names:
        matches = [s for s in scores if name.lower() in s["member_name"].lower()]
        for m in matches[:2]:
            print(
                f"  {m['member_name']} ({m['party']}-{m['state']}): "
                f"score={m['key_vote_score']}  "
                f"cast={m['votes_cast']}  pro_labor={m['pro_labor_votes']}"
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    api_key = get_congress_api_key()

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    federal_votes = config.get("federal_votes", [])
    log.info("Loaded %d federal vote definitions from config", len(federal_votes))

    actionable = [v for v in federal_votes if v.get("floor_vote") is not False and v.get("floor_vote") != "pending_verification" and v.get("vote_type") != "committee" and v.get("roll_call_number")]
    skipped = [v["id"] for v in federal_votes if v not in actionable]
    log.info("Actionable votes: %d  |  Skipped: %s", len(actionable), skipped)

    all_records: list[dict] = []
    for vote_cfg in federal_votes:
        records = process_vote_config(vote_cfg, api_key)
        all_records.extend(records)

    if not all_records:
        log.error("No vote records fetched. Check config and API key.")
        sys.exit(1)

    log.info("Total member-vote records: %d", len(all_records))
    write_csv(VOTES_CSV, VOTE_CSV_FIELDS, all_records)

    scores = compute_scores(all_records)
    write_csv(SCORES_CSV, SCORE_CSV_FIELDS, scores)

    print_validation_report(scores, all_records)
    log.info("Done.")


if __name__ == "__main__":
    main()
