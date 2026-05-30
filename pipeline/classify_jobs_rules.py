"""
Deterministic enrichment classifier — reproduces enrich_jobs.py API classifications.

Usage:
    # Enrich classified_jobs.json in-place (weekly cron):
    python -m pipeline.classify_jobs_rules

    # Compare accuracy against enriched_jobs.json ground truth:
    python -m pipeline.classify_jobs_rules --compare data/enriched_jobs.json

    # Custom input/output:
    python -m pipeline.classify_jobs_rules --input data/classified_jobs.json --output data/classified_jobs.json

Reads data/classified_jobs.json by default; writes back to the same file.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# experience_level — 3-bucket schema with confidence scores
# Buckets: "early-career" | "experienced" | "leadership"
# Confidence: 0.9=strong title signals, 0.7=moderate/role-type, 0.5=weak/no signal
# ---------------------------------------------------------------------------

# Leadership (0.9): unambiguous C-suite, VP, Executive Director, Director of X
_LEAD_STRONG_RE = re.compile(
    r'\b(executive\s+director|vice[\s-]?president|\bvp\b'
    r'|chief\s+\w+\s+officer|\bceo\b|\bcoo\b|\bcfo\b'
    r'|chief\s+of\s+staff|\bchief\b(?!\s+(?:shop\s+)?steward)'
    r'|director\s+of\s+\w+'
    r'|president(?!\s+of\s+(?:the|a)\b)'
    r'|general\s+counsel)\b',
    re.IGNORECASE,
)

# Leadership (0.7): director titles (without "of"), supervisors, lead-X patterns.
# NOTE: "senior"/"sr." removed — Senior X is "experienced" not "leadership" in labor context.
# Director/VP/Chief/President are leadership; "Senior Manager" is experienced.
_LEAD_MOD_RE = re.compile(
    r'\b('
    r'lead\s+(?:counsel|researcher|analyst|representative|attorney|coordinator)'
    r'|(?:deputy\s+)?director(?!\s+of\b)'
    r'|supervisor|business\s+agent'
    r')\b',
    re.IGNORECASE,
)

# New-to-labor (0.9 title / 0.7 description): fellowships, internships, apprenticeships,
# and training programs — people entering the labor movement for the first time.
# Fires BEFORE all early-career checks so these titles aren't caught downstream.
_NEW_TO_LABOR_TITLE_RE = re.compile(
    r'\b(intern(?:ship)?s?'
    r'|fellow(?:ship)?s?'
    r'|apprentice(?:ship)?s?'
    r'|entry[\s-]level'
    r'|organizers?[\s-]in[\s-]training'
    r'|training\s+program'
    r'|new\s+grad(?:uate)?s?'
    r'|recent\s+grad(?:uate)?s?'
    r')\b',
    re.IGNORECASE,
)

# Description-level new-to-labor signals (checked against title + first 500 chars of description)
_NEW_TO_LABOR_DESC_RE = re.compile(
    r'\b(no\s+(?:prior\s+)?experience\s+(?:is\s+)?required'
    r'|0\s+years?\s+(?:of\s+)?experience'
    r'|new\s+grad(?:uate)?s?'
    r'|recent\s+grad(?:uate)?s?'
    r')\b',
    re.IGNORECASE,
)

# Early-career (0.9): clerks, explicit junior/entry markers NOT already in new-to-labor.
# (intern/fellow/apprentice/entry-level/organizer-in-training moved to _NEW_TO_LABOR_TITLE_RE)
_EARLY_STRONG_RE = re.compile(
    r'\b(junior'
    r'|(?:specialist|representative|analyst|coordinator|organizer)\s+i\b'
    r'|\b(?:law|record|data|file)\s+clerk\b|\bclerk\s+i\b'
    r'|receptionist|(?:administrative|office|program)\s+assistant'
    r'|division\s+assistant|field\s+educational\s+assistant'
    r'|(?:worksite|construction[\s-]worker|lig|uaou)\s+organizer'
    r')\b',
    re.IGNORECASE,
)

# Early-career (0.7): associate roles (not Associate Director/VP/Dean/Counsel)
_EARLY_MOD_RE = re.compile(
    r'\bassociate\b(?!\s+(?:vice|dean|director|general|vp\b))',
    re.IGNORECASE,
)

# Scope/seniority qualifiers that block the Union job and coordinator early-career rules
# Includes institutional affiliations (UC campuses) and department names (contracts)
# that indicate experienced staff organizer positions rather than entry-level roles
_SCOPE_QUALIFIER_RE = re.compile(
    r'\b(national|regional|lead|senior|\bsr\.?|uc[a-z]*|contracts)\b',
    re.IGNORECASE,
)

# Coordinator suffix → early-career for exp 2/3 (unless preceded by seniority qualifier)
_COORDINATOR_RE = re.compile(r'\bcoordinator\b', re.IGNORECASE)

# Title keywords indicating experienced (not early-career) in Union job exp=2 context
_UNION_JOB_EXPERIENCED_RE = re.compile(
    r'\b(representative|specialist|negotiator|business\s+agent'
    r'|labor\s+relations|legislative|advocacy|governance|collective\s+bargaining'
    r'|business\s+rep(?:resentative)?|field\s+rep(?:resentative)?'
    r'|secretary|educator|engineer|programmer)\b',
    re.IGNORECASE,
)

# "Representative" in title: External/Internal organizer title is experienced-level
_REP_IN_TITLE_RE = re.compile(r'\brepresentative\b', re.IGNORECASE)


_TEMP_RE = re.compile(r'\btemporary\b', re.IGNORECASE)
_EXEC_ADMIN_ASSISTANT_RE = re.compile(
    r'\bexecutive\s+(?:administrative|program)\s+assistant\b'
    r'|\bexecutive\s+assistant\s+to\b',
    re.IGNORECASE,
)


def classify_experience(job: dict) -> Tuple[str, float]:
    title = (job.get("title") or "").strip()
    exp_int = job.get("exp_level")
    role_type = job.get("role_type") or ""

    # New-to-labor (0.9): fellowships, internships, apprenticeships, training programs.
    # Fires before all other checks — a fellowship is new-to-labor regardless of other signals.
    if _NEW_TO_LABOR_TITLE_RE.search(title):
        return "new-to-labor", 0.9

    # Description-level new-to-labor signals (lower confidence — description is noisier)
    desc_snippet = (job.get("description") or "")[:500]
    if _NEW_TO_LABOR_DESC_RE.search(title + " " + desc_snippet):
        return "new-to-labor", 0.7

    # Temporary roles are early-career regardless of title seniority signals
    if _TEMP_RE.search(title):
        return "early-career", 0.7

    # "Executive Administrative/Program Assistant" is experienced support staff, not early-career
    if _EXEC_ADMIN_ASSISTANT_RE.search(title):
        return "experienced", 0.5

    # Strong leadership (0.9): C-suite, VP, ED, Director of X, President
    if _LEAD_STRONG_RE.search(title):
        return "leadership", 0.9

    # Strong early-career (0.9): junior, clerks, explicit entry markers
    if _EARLY_STRONG_RE.search(title):
        return "early-career", 0.9

    # Moderate leadership (0.7): senior/sr., director, supervisor, lead-X
    if _LEAD_MOD_RE.search(title):
        return "leadership", 0.7

    # Moderate early-career (0.7): associate roles (non-director)
    if _EARLY_MOD_RE.search(title):
        return "early-career", 0.7

    # exp_level=1 → early-career (0.7)
    if exp_int == 1:
        return "early-career", 0.7

    # exp_level=4 without a clear leadership title → experienced (0.5)
    if exp_int == 4:
        return "experienced", 0.5

    # Coordinator suffix (exp 2/3, no seniority prefix) → early-career
    if (exp_int in (2, 3)
            and _COORDINATOR_RE.search(title)
            and not _SCOPE_QUALIFIER_RE.search(title)):
        return "early-career", 0.7

    if exp_int == 2:
        # Communications role_type → early-career (coordinators, organizers, entry comms staff)
        if role_type == "Communications" and not _SCOPE_QUALIFIER_RE.search(title):
            return "early-career", 0.7
        # External/Internal organizer without scope qualifier or representative title → early-career
        if (role_type in ("External organizer", "Internal organizer")
                and not _SCOPE_QUALIFIER_RE.search(title)
                and not _REP_IN_TITLE_RE.search(title)):
            return "early-career", 0.7
        # Union job without scope/experienced-level qualifier → early-career
        if (role_type == "Union job"
                and not _SCOPE_QUALIFIER_RE.search(title)
                and not _UNION_JOB_EXPERIENCED_RE.search(title)):
            return "early-career", 0.7

    # exp=2 or exp=3 → experienced (0.7)
    if exp_int in (2, 3):
        return "experienced", 0.7

    # No clear signal
    return "experienced", 0.5


# ---------------------------------------------------------------------------
# seniority_signals — keywords from title+description that triggered exp level
# ---------------------------------------------------------------------------
_SENIORITY_PATTERNS = [
    re.compile(r'\b(director)\b', re.IGNORECASE),
    re.compile(r'\b(vice[\s-]?president|vp)\b', re.IGNORECASE),
    re.compile(r'\b(chief)\b', re.IGNORECASE),
    re.compile(r'\b(executive)\b', re.IGNORECASE),
    re.compile(r'\b(president)\b', re.IGNORECASE),
    re.compile(r'\b(senior|sr\.?)\b', re.IGNORECASE),
    re.compile(r'\b(lead)\b', re.IGNORECASE),
    re.compile(r'\b(coordinator)\b', re.IGNORECASE),
    re.compile(r'\b(supervisor)\b', re.IGNORECASE),
    re.compile(r'\b(advocate)\b', re.IGNORECASE),
    re.compile(r'\b(fellow|fellowship)\b', re.IGNORECASE),
    re.compile(r'\b(intern|internship)\b', re.IGNORECASE),
    re.compile(r'\b(apprentice|apprenticeship)\b', re.IGNORECASE),
    re.compile(r'\b(entry[\s-]level)\b', re.IGNORECASE),
    re.compile(r'\b(associate organizer|new organizer|junior)\b', re.IGNORECASE),
    re.compile(r'\b(manager)\b', re.IGNORECASE),
]


def extract_seniority_signals(job: dict) -> List[str]:
    text = (job.get("title") or "") + " " + (job.get("description") or "")
    seen: Set[str] = set()
    signals: List[str] = []
    for pat in _SENIORITY_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(0).lower().strip()
            if val not in seen:
                seen.add(val)
                signals.append(val)
    return signals


# ---------------------------------------------------------------------------
# job_function — keyword rules (title first) then role_type mapping
# ---------------------------------------------------------------------------

# Technology: IT, software, data infrastructure/analytics roles
_TECH_RE = re.compile(
    r'\b(it\s+(?:director|manager|specialist|coordinator)|web\s+developer'
    r'|software\s+engineer|database\s+(?:admin|administrator|manager)'
    r'|tech\s+support|information\s+technology|systems\s+administrator'
    r'|data\s+engineer|cybersecurity|devops|helpdesk|network\s+administrator'
    r'|data\s+(?:director|manager|analytics\s+director|infrastructure)'
    r'|deputy\s+director.*data|analytics\s+(?:director|manager)'
    r'|infrastructure.*(?:data|tech))\b',
    re.IGNORECASE,
)

# Finance: accounting, payroll, budget roles
_FINANCE_RE = re.compile(
    r'\b(accountant|accounting|bookkeeper|payroll|treasurer|comptroller'
    r'|budget\s+(?:analyst|director|manager)|fiscal|auditor'
    r'|financial\s+analyst|finance\s+(?:director|manager|associate|coordinator)'
    r'|deputy\s+finance)\b',
    re.IGNORECASE,
)

# Political: campaigns, electoral, lobbying, civic engagement, advocacy
_POLITICAL_RE = re.compile(
    r'\b(political|electoral|legislat(?:ive|or)|lobby(?:ist|ing)?'
    r'|advocacy|voter\s+(?:access|outreach|registration|protection)'
    r'|get[\s-]out[\s-]the[\s-]vote|gotv|civic\s+engagement'
    r'|campaign\s+(?:manager|director|coordinator|organizer)'
    r'|ballot\s+(?:access|initiative)|field\s+director(?!\s+of\s+organizing)'
    r'|deputy\s+(?:statewide\s+)?field\s+director'
    r'|civil\s+rights|women[\'s]*\s+rights(?!\s+organizing)'
    r'|special\s+programming|ground\s+game|state\s+(?:lead|director)(?!.*union)'
    r'|regional\s+campaign)\b',
    re.IGNORECASE,
)

# Legal: attorneys, counsel, paralegals
_LEGAL_KW_RE = re.compile(
    r'\b(attorney|(?:general\s+)?counsel|paralegal|legal\s+(?:assistant|director|representative)'
    r'|labor\s+counsel|staff\s+attorney|senior\s+counsel)\b',
    re.IGNORECASE,
)

# Communications: press, media, messaging, creative, writing roles
_COMM_KW_RE = re.compile(
    r'\b(communications\s+(?:director|specialist|coordinator|manager|staff)'
    r'|press\s+(?:secretary|director)|media\s+(?:director|relations|strategist)'
    r'|messaging|digital\s+(?:director|strategist|organizer)'
    r'|creative\s+(?:director|lead|manager)|public\s+relations|graphic\s+designer'
    r'|content\s+(?:director|manager|strategist)|social\s+media'
    r'|marketing\s+(?:director|manager)|communications\b'
    r'|speechwriter|copywriter'
    r')\b',
    re.IGNORECASE,
)

# Research: researchers, analysts for policy/polling/data (not IT data)
_RESEARCH_RE = re.compile(
    r'\b(research(?:er)?|research\s+(?:analyst|director|associate|coordinator)'
    r'|policy\s+(?:analyst|director|researcher)'
    r'|polling\s+analyst|data\s+analyst(?!\s+(?:and|&)\s+infrastructure)'
    r'|strategic\s+researcher|research\s+and\s+organizer)\b',
    re.IGNORECASE,
)

# Organizing: explicit organizing titles to rescue from "other"
_ORGANIZING_RE = re.compile(
    r'\b(organizer|organizing|strategic\s+campaigns\s+director'
    r'|organizational\s+consultant|field\s+(?:representative|coordinator|staff)'
    r'|labor\s+representative|union\s+representative|member\s+(?:organizer|outreach)'
    r'|internal\s+(?:organizer|organizing)|external\s+(?:organizer|organizing)'
    r'|organizing\s+(?:director|manager|coordinator))\b',
    re.IGNORECASE,
)

ROLE_TYPE_TO_FUNCTION = {
    "Internal organizer":  "organizing",
    "External organizer":  "organizing",
    "Union job":           "organizing",
    "Apprenticeship":      "organizing",
    "Communications":      "communications",
    "Political/electoral": "political",
    "Research":            "research",
    "Legal":               "legal",
    "Admin/operations":    "operations",
}


def classify_job_function(job: dict) -> str:
    title = (job.get("title") or "")
    desc = (job.get("description") or "")
    # Title-only for high-precision checks; title+desc for broader checks
    title_and_desc = title + " " + desc

    # Technology and finance are narrow enough to check title+desc
    if _TECH_RE.search(title_and_desc):
        return "technology"
    if _FINANCE_RE.search(title_and_desc):
        return "finance"

    # Political — title only (description often mentions politics in non-political jobs)
    if _POLITICAL_RE.search(title):
        return "political"

    # Legal — title only
    if _LEGAL_KW_RE.search(title):
        return "legal"

    # Communications — title only
    if _COMM_KW_RE.search(title):
        return "communications"

    # Research — title only (avoid false positives from descriptions)
    if _RESEARCH_RE.search(title):
        # Policy analyst titles with "legislative" are political, not research
        if re.search(r'\blegislat\w*\b', title, re.IGNORECASE):
            return "political"
        return "research"

    # Explicit organizing title keywords (rescues Admin/operations misclassified as operations)
    if _ORGANIZING_RE.search(title):
        return "organizing"

    # Fall back to role_type mapping
    role_type = job.get("role_type") or ""
    return ROLE_TYPE_TO_FUNCTION.get(role_type, "other")


# ---------------------------------------------------------------------------
# location_type — regex on location_raw, fallback to is_remote boolean
# ---------------------------------------------------------------------------
_HYBRID_RE = re.compile(r'\bhybrid\b', re.IGNORECASE)
_REMOTE_RE = re.compile(r'\bremote\b', re.IGNORECASE)


def classify_location_type(job: dict) -> str:
    raw = job.get("location_raw") or ""
    if _HYBRID_RE.search(raw):
        return "hybrid"
    if _REMOTE_RE.search(raw):
        return "remote"
    if job.get("is_remote"):
        return "remote"
    return "in-person"


# ---------------------------------------------------------------------------
# location_parsed — region + airport lookup tables derived from enriched data
# ---------------------------------------------------------------------------
CITY_REGION_MAP: dict[str, str] = {
    # Northeast
    "New York":        "New York Metro",
    "Brooklyn":        "New York Metro",
    "Bronx":           "New York Metro",
    "Newark":          "New York Metro",
    "Albany":          "Northeast",
    "Buffalo":         "Northeast",
    "Boston":          "Northeast",
    "Providence":      "Northeast",
    "Hartford":        "Northeast",
    "New Haven":       "Northeast",
    "Philadelphia":    "Northeast",
    "Pittsburgh":      "Northeast",
    "Baltimore":       "Northeast",
    "Washington":      "Mid-Atlantic",
    "Richmond":        "Mid-Atlantic",
    # Southeast
    "Atlanta":         "Southeast",
    "Miami":           "Southeast",
    "Tampa":           "Southeast",
    "Orlando":         "Southeast",
    "Charlotte":       "Southeast",
    "Raleigh":         "Southeast",
    "Nashville":       "Southeast",
    "Memphis":         "Southeast",
    "Birmingham":      "Southeast",
    "New Orleans":     "Southeast",
    # Midwest
    "Chicago":         "Midwest",
    "Detroit":         "Midwest",
    "Cleveland":       "Midwest",
    "Columbus":        "Midwest",
    "Cincinnati":      "Midwest",
    "Indianapolis":    "Midwest",
    "Milwaukee":       "Midwest",
    "Minneapolis":     "Midwest",
    "St. Louis":       "Midwest",
    "Kansas City":     "Midwest",
    "Omaha":           "Midwest",
    # South/Southwest
    "Dallas":          "Texas",
    "Houston":         "Texas",
    "Austin":          "Texas",
    "San Antonio":     "Texas",
    "Phoenix":         "Southwest",
    "Tucson":          "Southwest",
    "Albuquerque":     "Southwest",
    "Denver":          "Mountain West",
    "Salt Lake City":  "Mountain West",
    "Las Vegas":       "Southwest",
    # West Coast
    "Los Angeles":     "Southern California",
    "San Diego":       "Southern California",
    "San Francisco":   "Bay Area",
    "Oakland":         "Bay Area",
    "San Jose":        "Bay Area",
    "Sacramento":      "Northern California",
    "Portland":        "Pacific Northwest",
    "Seattle":         "Pacific Northwest",
    "Tacoma":          "Pacific Northwest",
    "Anchorage":       "Alaska",
    "Honolulu":        "Hawaii",
    # Rock Tavern / other NY
    "Rock Tavern":     "Northeast",
    "Rochester":       "Northeast",
    "Syracuse":        "Northeast",
    "Yonkers":         "New York Metro",
}

STATE_REGION_MAP: dict[str, str] = {
    "ME": "Northeast", "NH": "Northeast", "VT": "Northeast",
    "MA": "Northeast", "RI": "Northeast", "CT": "Northeast",
    "NY": "Northeast", "NJ": "Northeast", "PA": "Northeast",
    "MD": "Mid-Atlantic", "DE": "Mid-Atlantic", "DC": "Mid-Atlantic",
    "VA": "Mid-Atlantic", "WV": "Mid-Atlantic",
    "NC": "Southeast", "SC": "Southeast", "GA": "Southeast",
    "FL": "Southeast", "AL": "Southeast", "MS": "Southeast",
    "TN": "Southeast", "KY": "Southeast",
    "OH": "Midwest", "IN": "Midwest", "IL": "Midwest",
    "MI": "Midwest", "WI": "Midwest", "MN": "Midwest",
    "IA": "Midwest", "MO": "Midwest", "ND": "Midwest",
    "SD": "Midwest", "NE": "Midwest", "KS": "Midwest",
    "LA": "Southeast", "AR": "Southeast", "OK": "Southwest",
    "TX": "Texas",
    "MT": "Mountain West", "ID": "Mountain West", "WY": "Mountain West",
    "CO": "Mountain West", "UT": "Mountain West", "NV": "Southwest",
    "AZ": "Southwest", "NM": "Southwest",
    "CA": "California", "OR": "Pacific Northwest", "WA": "Pacific Northwest",
    "AK": "Alaska", "HI": "Hawaii",
}

CITY_AIRPORT_MAP: dict[str, list[str]] = {
    "New York":        ["JFK", "LGA", "EWR"],
    "Brooklyn":        ["JFK", "LGA", "EWR"],
    "Newark":          ["EWR", "JFK", "LGA"],
    "Boston":          ["BOS"],
    "Philadelphia":    ["PHL"],
    "Washington":      ["DCA", "IAD", "BWI"],
    "Baltimore":       ["BWI", "DCA"],
    "Atlanta":         ["ATL"],
    "Miami":           ["MIA", "FLL"],
    "Chicago":         ["ORD", "MDW"],
    "Detroit":         ["DTW"],
    "Minneapolis":     ["MSP"],
    "Dallas":          ["DFW", "DAL"],
    "Houston":         ["IAH", "HOU"],
    "Denver":          ["DEN"],
    "Los Angeles":     ["LAX", "BUR", "LGB"],
    "San Francisco":   ["SFO", "OAK", "SJC"],
    "Oakland":         ["OAK", "SFO"],
    "San Jose":        ["SJC", "SFO", "OAK"],
    "Seattle":         ["SEA"],
    "Portland":        ["PDX"],
    "Phoenix":         ["PHX"],
    "Las Vegas":       ["LAS"],
    "Salt Lake City":  ["SLC"],
    "Kansas City":     ["MCI"],
    "St. Louis":       ["STL"],
    "New Orleans":     ["MSY"],
    "Nashville":       ["BNA"],
    "Charlotte":       ["CLT"],
    "Pittsburgh":      ["PIT"],
    "Cleveland":       ["CLE"],
}


# Detects location_raw strings that describe a multi-state region rather than a specific city.
# When matched (and no specific city was parsed), state_abbr is discarded — it was likely
# scraped from a state abbreviation inside the regional list (e.g. "CT, DE, MA…" → "DE").
_REGION_SPAN_RE = re.compile(
    r'\b(?:the\s+)?(northeast|midwest|southeast|southwest|northwest|west\s+coast|east\s+coast)\b',
    re.IGNORECASE,
)
_REGION_INFERRED: dict[str, str] = {
    'northeast':  'Northeast',
    'midwest':    'Midwest',
    'southeast':  'Southeast',
    'southwest':  'Southwest',
    'northwest':  'Pacific Northwest',
    'west coast': 'Pacific Northwest',
    'east coast': 'Northeast',
}

# Full state name → abbreviation. Used to infer state when location_raw is a bare state name
# ("New Jersey", "California", "Statewide in California") but state_abbr wasn't set by the scraper.
_FULL_STATE_NAME_MAP: dict[str, str] = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'district of columbia': 'DC', 'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI',
    'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
    'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
    'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
    'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
    'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
    'vermont': 'VT', 'west virginia': 'WV', 'virginia': 'VA', 'washington': 'WA',
    'wisconsin': 'WI', 'wyoming': 'WY',
}


def _sanitize_city(city: Optional[str]) -> Optional[str]:
    """
    Fix garbled city values produced by the location parser.

    Cases handled:
    - "Remote to start but must be in Oakland" → None  (remote job; city is noise)
    - "Campaign Washington"                   → "Washington"  (leading label stripped)
    - "New York" / "Oakland"                  → unchanged (already known)
    """
    if not city:
        return None
    # Starts with "Remote" → city is meaningless (remote + eventual target city)
    if re.match(r'^remote\b', city, re.IGNORECASE):
        return None
    # Known city → pass through immediately
    if city in CITY_REGION_MAP:
        return city
    # Multi-word city: leading word may be a noise token (badge, category label).
    # Try last 2 words, then last 1 word, against the known-city map.
    words = city.split()
    if len(words) > 1:
        for n in (2, 1):
            candidate = " ".join(words[-n:])
            if candidate in CITY_REGION_MAP:
                return candidate
    return city  # unknown city — keep as-is rather than drop


def classify_location_parsed(job: dict) -> dict:
    city = job.get("city") or None
    state = job.get("state_abbr") or None
    raw = job.get("location_raw") or ""

    # Sanitize garbled city values before any lookup
    city = _sanitize_city(city)

    # Infer state from a bare full state name in location_raw when neither city nor
    # state_abbr was populated by the scraper (e.g. "New Jersey", "Statewide in California").
    if city is None and state is None and raw:
        raw_lower = raw.strip().lower()
        for sname, sabb in _FULL_STATE_NAME_MAP.items():
            if sname in raw_lower:
                state = sabb
                break

    # When location_raw is a multi-state regional description and no specific city
    # was parsed, discard the scraped state (which was likely a false positive from
    # a state abbreviation embedded inside the region list) and infer region only.
    if city is None:
        m = _REGION_SPAN_RE.search(raw)
        if m:
            region_key = m.group(1).lower()
            return {
                "city":          None,
                "state":         None,
                "region":        _REGION_INFERRED.get(region_key),
                "near_airports": [],
                "raw":           raw,
            }

    region: Optional[str] = None
    if city:
        region = CITY_REGION_MAP.get(city)
    if region is None and state:
        region = STATE_REGION_MAP.get(state)

    near_airports: List[str] = []
    if city:
        near_airports = CITY_AIRPORT_MAP.get(city, [])

    return {
        "city":          city,
        "state":         state,
        "region":        region,
        "near_airports": near_airports,
        "raw":           raw,
    }


# ---------------------------------------------------------------------------
# union_affiliation — infer parent union from employer name
# ---------------------------------------------------------------------------
_UNION_AFFILIATION_PATTERNS = [
    (re.compile(r'SEIU', re.IGNORECASE), "SEIU"),
    (re.compile(r'\bAFSCME\b', re.IGNORECASE), "AFSCME"),
    (re.compile(r'\bCWA\b', re.IGNORECASE), "CWA"),
    (re.compile(r'\bUAW\b', re.IGNORECASE), "UAW"),
    (re.compile(r'\bTeamsters?\b', re.IGNORECASE), "Teamsters"),
    (re.compile(r'\bUFCW\b', re.IGNORECASE), "UFCW"),
    (re.compile(r'\bAFT\b', re.IGNORECASE), "AFT"),
    (re.compile(r'\bNEA\b', re.IGNORECASE), "NEA"),
    (re.compile(r'\bIBEW\b', re.IGNORECASE), "IBEW"),
    (re.compile(r'\bUSW\b', re.IGNORECASE), "USW"),
    (re.compile(r'\bUNITE\s+HERE\b', re.IGNORECASE), "UNITE HERE"),
    (re.compile(r'\bLIUNA\b', re.IGNORECASE), "LIUNA"),
    (re.compile(r'\bIBT\b', re.IGNORECASE), "IBT"),
    (re.compile(r'\bAFL[\s-]CIO\b', re.IGNORECASE), "AFL-CIO"),
    (re.compile(r'\bIAFF\b', re.IGNORECASE), "IAFF"),
    (re.compile(r'\bNNU\b|National\s+Nurses\s+United', re.IGNORECASE), "NNU"),
]


def classify_union_affiliation(job: dict) -> Optional[str]:
    employer = (job.get("employer") or "").strip()
    title = (job.get("title") or "").strip()
    text = employer + " " + title
    for pattern, affiliation in _UNION_AFFILIATION_PATTERNS:
        if pattern.search(text):
            return affiliation
    return None


# ---------------------------------------------------------------------------
# employment_type — infer from title + description
# ---------------------------------------------------------------------------
_TEMP_TYPE_RE = re.compile(
    r'\b(temporary|temp\b|limited[\s-]term|short[\s-]term|seasonal)\b',
    re.IGNORECASE,
)
_PART_TIME_RE = re.compile(r'\bpart[\s-]time\b', re.IGNORECASE)
_CONTRACT_RE = re.compile(r'\b(contract(?:or)?|freelance|consultant)\b', re.IGNORECASE)


def classify_employment_type(job: dict) -> str:
    title = (job.get("title") or "")
    desc = (job.get("description") or "")[:1000]
    text = title + " " + desc
    if _TEMP_TYPE_RE.search(text):
        return "temporary"
    if _PART_TIME_RE.search(text):
        return "part-time"
    if _CONTRACT_RE.search(text):
        return "contract"
    return "full-time"


# ---------------------------------------------------------------------------
# supervisory — boolean: does this role manage people?
# ---------------------------------------------------------------------------
_SUPERVISORY_DESC_RE = re.compile(
    r'\b(supervise[sd]?|supervision|direct\s+reports?|staff\s+of\s+\d+|leads?\s+a\s+team'
    r'|manages?\s+\d+|managing\s+staff|manage\s+a\s+team|oversee\s+(?:a\s+)?(?:team|staff)'
    r'|manage\s+(?:a\s+)?(?:team|staff)|lead\s+(?:a\s+)?team|personnel\s+management'
    r'|supervising\s+staff|management\s+of\s+staff)\b',
    re.IGNORECASE,
)


def classify_supervisory(job: dict) -> bool:
    desc = (job.get("description") or "")
    if _SUPERVISORY_DESC_RE.search(desc):
        return True
    # Leadership titles with director/manager/supervisor in title are supervisory
    title = (job.get("title") or "")
    exp_level = job.get("experience_level") or classify_experience(job)[0]
    if exp_level == "leadership" and re.search(
        r'\b(director|manager|supervisor|chief|president|VP|vice[\s-]?president)\b',
        title, re.IGNORECASE
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# professional_staff — "professional" | "staff"
# ---------------------------------------------------------------------------
_PROFESSIONAL_TITLE_RE = re.compile(
    r'\b(attorney|lawyer|counsel|accountant|\bcpa\b|engineer|analyst|doctor|nurse|physician'
    r'|architect|scientist|researcher|economist|epidemiologist|actuary|statistician'
    r'|psychologist|social\s+worker|therapist|pharmacist|dentist)\b',
    re.IGNORECASE,
)
_STAFF_TITLE_RE = re.compile(
    r'\b(organizer|field\s+rep(?:resentative)?|coordinator|representative|specialist'
    r'|administrator|assistant|clerk|receptionist|technician|liaison|outreach'
    r'|advocate|canvasser|steward|delegate)\b',
    re.IGNORECASE,
)


def classify_professional_staff(job: dict) -> str:
    title = (job.get("title") or "")
    if _PROFESSIONAL_TITLE_RE.search(title):
        return "professional"
    return "staff"


# ---------------------------------------------------------------------------
# special_requirements — expand existing list from description
# ---------------------------------------------------------------------------
_SPECIAL_REQ_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\bbilingual\b', re.IGNORECASE), "bilingual"),
    (re.compile(r'\b(CDL|commercial\s+driver(?:\'s)?\s+license)\b', re.IGNORECASE), "CDL"),
    (re.compile(
        r'\b(physical\s+(?:demands?|requirements?)|physically\s+(?:demanding|active))\b',
        re.IGNORECASE
    ), "physical demands"),
    (re.compile(r'\birregular\s+hours?\b', re.IGNORECASE), "irregular hours"),
    (re.compile(r'\bon[\s-]call\b', re.IGNORECASE), "on-call"),
    (re.compile(
        r'\b(valid\s+driver[\'s]*\s+license|driver[\'s]*\s+license\s+required|must\s+have\s+(?:a\s+)?(?:valid\s+)?driver)\b',
        re.IGNORECASE
    ), "driver's license"),
    (re.compile(
        r'\b(must\s+have\s+(?:a\s+)?(?:reliable\s+)?(?:car|vehicle)|reliable\s+transportation|own\s+(?:vehicle|car))\b',
        re.IGNORECASE
    ), "reliable transportation"),
    (re.compile(r'\btravel\s+(?:required|extensive|frequently|up\s+to)\b', re.IGNORECASE), "travel required"),
    (re.compile(r'\bevening[s]?\s+and\s+weekend[s]?\b|\bweekends?\s+(?:and|&)\s+evening[s]?\b', re.IGNORECASE), "evenings and weekends"),
]


def expand_special_requirements(job: dict) -> List[str]:
    existing = list(job.get("special_requirements") or [])
    existing_lower = {s.lower() for s in existing}
    desc = (job.get("description") or "") + " " + (job.get("title") or "")
    for pattern, label in _SPECIAL_REQ_PATTERNS:
        if label.lower() not in existing_lower and pattern.search(desc):
            existing.append(label)
            existing_lower.add(label.lower())
    return existing


# ---------------------------------------------------------------------------
# credentials_required — professional certifications/degrees in description
# ---------------------------------------------------------------------------
_CREDENTIALS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\b(J\.?D\.?|Juris\s+Doctor)\b', re.IGNORECASE), "JD"),
    (re.compile(r'\b(C\.?P\.?A\.?|Certified\s+Public\s+Accountant)\b', re.IGNORECASE), "CPA"),
    (re.compile(r'\b(L\.?C\.?S\.?W\.?|Licensed\s+Clinical\s+Social\s+Worker)\b', re.IGNORECASE), "LCSW"),
    (re.compile(r'\b(L\.?M\.?S\.?W\.?|Licensed\s+Master\s+Social\s+Worker)\b', re.IGNORECASE), "LMSW"),
    (re.compile(r'\b(M\.?S\.?W\.?|Master\s+of\s+Social\s+Work)\b', re.IGNORECASE), "MSW"),
    (re.compile(r'\b(R\.?N\.?|Registered\s+Nurse)\b', re.IGNORECASE), "RN"),
    (re.compile(r'\b(L\.?P\.?N\.?|Licensed\s+Practical\s+Nurse)\b', re.IGNORECASE), "LPN"),
    (re.compile(r'\b(Ph\.?D\.?|Doctor\s+of\s+Philosophy)\b', re.IGNORECASE), "PhD"),
    (re.compile(r'\b(M\.?P\.?H\.?|Master\s+of\s+Public\s+Health)\b', re.IGNORECASE), "MPH"),
    (re.compile(r'\b(M\.?B\.?A\.?|Master\s+of\s+Business\s+Administration)\b', re.IGNORECASE), "MBA"),
    (re.compile(r'\bbar\s+admission\b|\badmitted\s+to\s+(?:the\s+)?bar\b', re.IGNORECASE), "bar admission"),
]


def extract_credentials_required(job: dict) -> List[str]:
    desc = (job.get("description") or "") + " " + (job.get("title") or "")
    found: List[str] = []
    seen: Set[str] = set()
    for pattern, label in _CREDENTIALS_PATTERNS:
        if label not in seen and pattern.search(desc):
            found.append(label)
            seen.add(label)
    return found


# ---------------------------------------------------------------------------
# benefits_signals — benefits mentioned in description
# ---------------------------------------------------------------------------
_BENEFITS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\bhealth\s+insurance\b', re.IGNORECASE), "health insurance"),
    (re.compile(r'\bmedical\s+(?:insurance|coverage|benefits?)\b', re.IGNORECASE), "medical"),
    (re.compile(r'\bdental\b', re.IGNORECASE), "dental"),
    (re.compile(r'\bvision\b', re.IGNORECASE), "vision"),
    (re.compile(r'\bpension\b', re.IGNORECASE), "pension"),
    (re.compile(r'\b403[\s-]?b\b', re.IGNORECASE), "403b"),
    (re.compile(r'\b401[\s-]?k\b', re.IGNORECASE), "401k"),
    (re.compile(r'\bretirement\b', re.IGNORECASE), "retirement"),
    (re.compile(r'\bpaid\s+time\s+off\b|\bPTO\b', re.IGNORECASE), "PTO"),
    (re.compile(r'\bvacation\b', re.IGNORECASE), "vacation"),
    (re.compile(r'\bsick\s+(?:leave|time|days?)\b', re.IGNORECASE), "sick leave"),
    (re.compile(r'\bcar\s+allowance\b', re.IGNORECASE), "car allowance"),
    (re.compile(r'\bcell\s+phone\b|\bphone\s+stipend\b', re.IGNORECASE), "cell phone"),
    (re.compile(r'\bremote\s+work\s+stipend\b|\bwork[\s-]from[\s-]home\s+stipend\b', re.IGNORECASE), "remote work stipend"),
    (re.compile(r'\blife\s+insurance\b', re.IGNORECASE), "life insurance"),
    (re.compile(r'\bparental\s+leave\b|\bmaternity\b|\bpaternity\b', re.IGNORECASE), "parental leave"),
    (re.compile(r'\btuition\s+(?:reimbursement|assistance|benefit)\b', re.IGNORECASE), "tuition reimbursement"),
]


def extract_benefits_signals(job: dict) -> List[str]:
    desc = (job.get("description") or "")
    found: List[str] = []
    seen: Set[str] = set()
    for pattern, label in _BENEFITS_PATTERNS:
        if label not in seen and pattern.search(desc):
            found.append(label)
            seen.add(label)
    return found


# ---------------------------------------------------------------------------
# years_experience — minimum years mentioned in description
# ---------------------------------------------------------------------------
_YEARS_EXP_RE = re.compile(
    r'(\d+)\+?\s+years?\s+(?:of\s+)?(?:experience|relevant\s+experience|professional\s+experience|related\s+experience|work\s+experience)'
    r'|minimum\s+(?:of\s+)?(\d+)\s+years?'
    r'|at\s+least\s+(\d+)\s+years?'
    r'|(\d+)[\s-]+to[\s-]+\d+\s+years?\s+(?:of\s+)?(?:experience|work)',
    re.IGNORECASE,
)


def extract_years_experience(job: dict) -> Optional[int]:
    desc = (job.get("description") or "")
    matches = _YEARS_EXP_RE.findall(desc)
    if not matches:
        return None
    nums = []
    for m in matches:
        for g in m:
            if g:
                try:
                    v = int(g)
                    if 0 < v <= 20:  # cap at 20 to exclude founding-year false positives
                        nums.append(v)
                except ValueError:
                    pass
    return min(nums) if nums else None


# ---------------------------------------------------------------------------
# background_required — domain experience signals in description
# ---------------------------------------------------------------------------
_BACKGROUND_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\blabor\s+movement\b', re.IGNORECASE), "labor movement"),
    (re.compile(r'\bunion\s+(?:experience|background|staff|member)\b', re.IGNORECASE), "union experience"),
    (re.compile(r'\bcampaign\s+experience\b', re.IGNORECASE), "campaign experience"),
    (re.compile(r'\borganizing\s+experience\b', re.IGNORECASE), "organizing experience"),
    (re.compile(r'\blegislative\s+experience\b', re.IGNORECASE), "legislative experience"),
    (re.compile(r'\blegal\s+background\b|\blegal\s+experience\b', re.IGNORECASE), "legal background"),
    (re.compile(r'\bpolitical\s+(?:experience|background|campaigns?)\b', re.IGNORECASE), "political experience"),
    (re.compile(r'\bnonprofit\s+(?:experience|background|sector)\b', re.IGNORECASE), "nonprofit experience"),
    (re.compile(r'\bcommunity\s+organizing\b', re.IGNORECASE), "community organizing"),
    (re.compile(r'\blocal\s+government\b|\bpublic\s+sector\s+(?:experience|background)\b', re.IGNORECASE), "public sector experience"),
    (re.compile(r'\bdata\s+(?:analysis|analytics)\s+experience\b', re.IGNORECASE), "data analysis experience"),
    (re.compile(r'\bcollective\s+bargaining\b', re.IGNORECASE), "collective bargaining"),
]


def extract_background_required(job: dict) -> List[str]:
    desc = (job.get("description") or "")
    found: List[str] = []
    seen: Set[str] = set()
    for pattern, label in _BACKGROUND_PATTERNS:
        if label not in seen and pattern.search(desc):
            found.append(label)
            seen.add(label)
    return found


# ---------------------------------------------------------------------------
# Main enrichment function
# ---------------------------------------------------------------------------
def enrich_job(job: dict) -> dict:
    level, confidence = classify_experience(job)

    # Arena HTML cards embed employer in title as "EMPLOYER: Job Title".
    # Extract it here so existing records get populated without re-ingesting.
    employer = job.get("employer") or None
    if not employer and job.get("source_board") == "Arena":
        title = job.get("title") or ""
        if ":" in title:
            extracted = title.split(":", 1)[0].strip()
            if extracted:
                employer = extracted

    # Build a partial job dict with experience_level so supervisory can use it
    partial = {**job, "employer": employer, "experience_level": level}

    return {
        **job,
        "employer":              employer,
        "experience_level":      level,
        "experience_confidence": confidence,
        "job_function":          classify_job_function(job),
        "location_type":         classify_location_type(job),
        "location_parsed":       classify_location_parsed(job),
        "seniority_signals":     extract_seniority_signals(job),
        # Intelligence card fields (Phase 2)
        "union_affiliation":     classify_union_affiliation(partial),
        "employment_type":       classify_employment_type(job),
        "supervisory":           classify_supervisory(partial),
        "professional_staff":    classify_professional_staff(job),
        "special_requirements":  expand_special_requirements(job),
        "credentials_required":  extract_credentials_required(job),
        "benefits_signals":      extract_benefits_signals(job),
        "years_experience":      extract_years_experience(job),
        "background_required":   extract_background_required(job),
    }


# ---------------------------------------------------------------------------
# Accuracy comparison
# Maps old 4-bucket ground truth (entry/mid/senior/executive) → new 3-bucket
# ---------------------------------------------------------------------------
COMPARE_FIELDS = ["experience_level", "job_function", "location_type"]

# Maps old 4-bucket GT values (entry/mid/senior/executive) to current 3+1 bucket schema.
_EXP_REMAP = {
    "entry":     "early-career",
    "mid":       "experienced",
    "senior":    "leadership",
    "executive": "leadership",
}

# Normalizes rules output when comparing against GT that predates the new-to-labor bucket.
# new-to-labor is a sub-type of early-career, so it counts as a match when GT says "early-career".
_RULES_EXP_NORMALIZE = {
    "new-to-labor": "early-career",
}


def compare_accuracy(rules_results: List[dict], ground_truth: List[dict]) -> dict:
    gt_by_id = {j["job_id"]: j for j in ground_truth if j.get("job_id") and j.get("_enriched")}
    totals: Counter = Counter()
    matches: Counter = Counter()

    for job in rules_results:
        jid = job.get("job_id")
        gt = gt_by_id.get(jid)
        if gt is None:
            continue
        for field in COMPARE_FIELDS:
            gt_val = gt.get(field)
            rules_val = job.get(field)
            if gt_val is None:
                continue
            totals[field] += 1
            if field == "experience_level":
                # Remap GT old 4-bucket values → current schema
                gt_val = _EXP_REMAP.get(gt_val, gt_val)
                # Normalize rules new-to-labor → early-career (GT predates the new bucket)
                rules_val = _RULES_EXP_NORMALIZE.get(rules_val, rules_val)
            if gt_val == rules_val:
                matches[field] += 1

    return {
        field: (matches[field] / totals[field] if totals[field] else 0.0)
        for field in COMPARE_FIELDS
    }


def print_accuracy_report(rates: dict) -> None:
    print("\n── Accuracy vs enriched_jobs.json ──────────────────────")
    all_pass = True
    for field, rate in rates.items():
        status = "✓" if rate >= 0.80 else "✗ BELOW 80%"
        print(f"  {field:<20} {rate:.1%}  {status}")
        if rate < 0.80:
            all_pass = False
    print("────────────────────────────────────────────────────────")
    if all_pass:
        print("  All fields ≥ 80% — rules classifier meets target.")
    else:
        print("  One or more fields below 80% — iterate rules before wiring into cron.")


# ---------------------------------------------------------------------------
# CLASSIFICATION_LOGIC.md — living-document updater
# ---------------------------------------------------------------------------
_DOC_PATH = Path(__file__).parent.parent / "CLASSIFICATION_LOGIC.md"


def update_classification_logic_doc(changelog_msg: Optional[str] = None) -> None:
    """
    Update CLASSIFICATION_LOGIC.md:
      - Refresh the '_Last updated: YYYY-MM-DD' timestamp to today.
      - If changelog_msg is provided, append a row to the Changelog table.

    Safe to call even if the doc doesn't exist yet (no-op with a warning).
    """
    from datetime import date

    if not _DOC_PATH.exists():
        print(f"Warning: {_DOC_PATH} not found — skipping doc update.")
        return

    today = date.today().isoformat()
    text = _DOC_PATH.read_text(encoding="utf-8")

    # Update the timestamp line (first occurrence of the pattern)
    text = re.sub(
        r"_Last updated:\s*\d{4}-\d{2}-\d{2}_",
        f"_Last updated: {today}_",
        text,
        count=1,
    )

    # Append changelog entry if a message was provided
    if changelog_msg:
        # Find the Changelog section and locate the last table row (line starting with |).
        # Insert the new row immediately after it.
        new_row = f"| {today} | {changelog_msg} |"
        # Match the Changelog section header through its last | row, then capture
        # whatever follows (blank line / next section).
        text = re.sub(
            r"(## Changelog\b.*?)(\n\n|\n(?![\|]))",
            lambda m: m.group(0),  # will be replaced properly below
            text,
            count=1,
            flags=re.DOTALL,
        )
        # Simpler: find the last | row before the next ## heading or ---
        changelog_section = re.search(
            r"(## Changelog\b.*?)(\n---|\n## )",
            text,
            re.DOTALL,
        )
        if changelog_section:
            section_text = changelog_section.group(1)
            # Find position of last | row within the section
            last_pipe = section_text.rfind("\n|")
            if last_pipe != -1:
                insert_at = changelog_section.start(1) + last_pipe + 1  # after the \n
                # Find end of that row
                row_end = text.index("\n", insert_at) + 1
                text = text[:row_end] + new_row + "\n" + text[row_end:]

    _DOC_PATH.write_text(text, encoding="utf-8")
    msg = f"Updated {_DOC_PATH.name}: timestamp → {today}"
    if changelog_msg:
        msg += f"; changelog: {changelog_msg!r}"
    print(msg)


def main():
    parser = argparse.ArgumentParser(description="Enrich jobs with deterministic rules")
    parser.add_argument("--input",     default="data/classified_jobs.json")
    parser.add_argument("--output",    default="data/classified_jobs.json")
    parser.add_argument("--compare",   default=None, help="Path to enriched_jobs.json for accuracy check")
    parser.add_argument("--changelog", default=None,
                        help="One-line description of rule changes made; appended to CLASSIFICATION_LOGIC.md")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        jobs = json.load(f)

    enriched = [enrich_job(j) for j in jobs]

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    # Summary
    exp_counts: Counter = Counter(j["experience_level"] for j in enriched)
    conf_counts: Counter = Counter(j.get("experience_confidence") for j in enriched)
    func_counts: Counter = Counter(j["job_function"] for j in enriched)
    loc_counts: Counter = Counter(j["location_type"] for j in enriched)

    print(f"Enriched: {len(enriched)} jobs → {args.output}")
    print(f"experience_level:      {dict(exp_counts.most_common())}")
    print(f"experience_confidence: {dict(conf_counts.most_common())}")
    print(f"job_function:          {dict(func_counts.most_common())}")
    print(f"location_type:         {dict(loc_counts.most_common())}")

    if args.compare:
        with open(args.compare, encoding="utf-8") as f:
            ground_truth = json.load(f)
        rates = compare_accuracy(enriched, ground_truth)
        print_accuracy_report(rates)

    # Always refresh the doc timestamp; optionally append a changelog entry
    update_classification_logic_doc(changelog_msg=args.changelog)


if __name__ == "__main__":
    main()
