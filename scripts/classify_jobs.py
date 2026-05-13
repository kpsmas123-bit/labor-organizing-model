#!/usr/bin/env python3
"""
Task 3: Classify and unify job listings into jobs_data.json.
Inputs:  output/unionjobs_raw.json, data/county_scores.json
Output:  output/jobs_data.json
"""

import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIONJOBS_RAW  = os.path.join(ROOT, "output", "unionjobs_raw.json")
COUNTY_SCORES  = os.path.join(ROOT, "data",   "county_scores.json")
OUTPUT_PATH    = os.path.join(ROOT, "output", "jobs_data.json")

# ── user profile weight constants (tune here) ─────────────────────────────────
# Weights must sum to 1.0 per profile.
# svs_weight:        strategic sector value (SVS score)
# distance_weight:   proximity to user's home location
# role_match_weight: role type alignment (staff / R2 / R3 / R4)
# sector_weight:     local organizing opportunity (OOS terrain score)
USER_PROFILES = {
    "entry_local": {
        "svs_weight":        0.15,
        "distance_weight":   0.40,
        "role_match_weight": 0.35,
        "sector_weight":     0.10,
    },
    "entry_relocate": {
        "svs_weight":        0.30,
        "distance_weight":   0.15,
        "role_match_weight": 0.35,
        "sector_weight":     0.20,
    },
    "experienced_relocate": {
        "svs_weight":        0.45,
        "distance_weight":   0.05,
        "role_match_weight": 0.25,
        "sector_weight":     0.25,
    },
}

# Used when no user profile is supplied at runtime.
DEFAULT_USER_PROFILE = {
    "type":     "entry_relocate",
    "home_lat": None,
    "home_lon": None,
}

# ── swing state bonus (reduced from 15 → 8) ──────────────────────────────────
SWING_STATE_BONUS = 8

SWING_STATES = {"PA", "WI", "MI", "AZ", "GA", "NV", "NC"}

# ── SVS by sector (public sector now split into sub-types) ───────────────────
SVS_BY_SECTOR = {
    "Healthcare":                     100,
    "Education":                      100,
    "Public Sector - Healthcare":     100,
    "Public Sector - Education":      100,
    "Public Sector - Local Government": 60,
    "Public Sector - State":           45,
    "Public Sector - Federal":         30,
    "Logistics/Warehousing":           75,
    "Building Trades":                 50,
    "Manufacturing":                   25,
    "Legal/Research":                  10,
    "Communications/Digital":          10,
    "Finance/Admin":                   10,
    "Other":                           10,
}

INTERVENTION_MAP = {
    "Type A: Organize Unorganized": "A",
    "Type B: Political Activation":  "B",
    "Type C: Partnership":           "C",
}

# ── seniority title keywords ─────────────────────────────────────────────────
SENIOR_TITLE_KEYWORDS = [
    "director", "manager", "senior", " vp ", "vice president", "vice-president",
    " lead ", "lead,", "lead-", "chief", "deputy", "coordinator",
]

ENTRY_TITLE_KEYWORDS = [
    "fellow", "fellowship", "intern", "internship",
    "new organizer", "field organizer", "external organizer",
    "organizing associate",
]

# ── state centroids (lat, lon) for distance fallback ─────────────────────────
STATE_CENTROIDS = {
    "AL": (32.806671,  -86.791130), "AK": (61.370716, -152.404419),
    "AZ": (33.729759, -111.431221), "AR": (34.969704,  -92.373123),
    "CA": (36.116203, -119.681564), "CO": (39.059811, -105.311104),
    "CT": (41.597782,  -72.755371), "DE": (39.318523,  -75.507141),
    "FL": (27.766279,  -81.686783), "GA": (33.040619,  -83.643074),
    "HI": (21.094318, -157.498337), "ID": (44.240459, -114.478828),
    "IL": (40.349457,  -88.986137), "IN": (39.849426,  -86.258278),
    "IA": (42.011539,  -93.210526), "KS": (38.526600,  -96.726486),
    "KY": (37.668140,  -84.670067), "LA": (31.169960,  -91.867805),
    "ME": (44.693947,  -69.381927), "MD": (39.063946,  -76.802101),
    "MA": (42.230171,  -71.530106), "MI": (43.326618,  -84.536095),
    "MN": (45.694454,  -93.900192), "MS": (32.741646,  -89.678696),
    "MO": (38.456085,  -92.288368), "MT": (46.921925, -110.454353),
    "NE": (41.125370,  -98.268082), "NV": (38.313515, -117.055374),
    "NH": (43.452492,  -71.563896), "NJ": (40.298904,  -74.521011),
    "NM": (34.840515, -106.248482), "NY": (42.165726,  -74.948051),
    "NC": (35.630066,  -79.806419), "ND": (47.528912,  -99.784012),
    "OH": (40.388783,  -82.764915), "OK": (35.565342,  -96.928917),
    "OR": (44.572021, -122.070938), "PA": (40.590752,  -77.209755),
    "RI": (41.680893,  -71.511780), "SC": (33.856892,  -80.945007),
    "SD": (44.299782,  -99.438828), "TN": (35.747845,  -86.692345),
    "TX": (31.054487,  -97.563461), "UT": (40.150032, -111.862434),
    "VT": (44.045876,  -72.710686), "VA": (37.769337,  -78.169968),
    "WA": (47.400902, -121.490494), "WV": (38.491226,  -80.954453),
    "WI": (44.268543,  -89.616508), "WY": (42.755966, -107.302490),
    "DC": (38.897438,  -77.026817),
}

# ── major city coords for distance lookup ─────────────────────────────────────
MAJOR_CITY_COORDS = {
    "new york":        (40.7128,  -74.0060),
    "los angeles":     (34.0522, -118.2437),
    "chicago":         (41.8781,  -87.6298),
    "houston":         (29.7604,  -95.3698),
    "phoenix":         (33.4484, -112.0740),
    "philadelphia":    (39.9526,  -75.1652),
    "san antonio":     (29.4241,  -98.4936),
    "san diego":       (32.7157, -117.1611),
    "dallas":          (32.7767,  -96.7970),
    "san jose":        (37.3382, -121.8863),
    "austin":          (30.2672,  -97.7431),
    "jacksonville":    (30.3322,  -81.6557),
    "fort worth":      (32.7555,  -97.3308),
    "columbus":        (39.9612,  -82.9988),
    "charlotte":       (35.2271,  -80.8431),
    "san francisco":   (37.7749, -122.4194),
    "indianapolis":    (39.7684,  -86.1581),
    "seattle":         (47.6062, -122.3321),
    "denver":          (39.7392, -104.9903),
    "washington":      (38.9072,  -77.0369),
    "nashville":       (36.1627,  -86.7816),
    "oklahoma city":   (35.4676,  -97.5164),
    "el paso":         (31.7619, -106.4850),
    "boston":          (42.3601,  -71.0589),
    "portland":        (45.5051, -122.6750),
    "las vegas":       (36.1699, -115.1398),
    "memphis":         (35.1495,  -90.0490),
    "louisville":      (38.2527,  -85.7585),
    "baltimore":       (39.2904,  -76.6122),
    "milwaukee":       (43.0389,  -87.9065),
    "albuquerque":     (35.0844, -106.6504),
    "tucson":          (32.2226, -110.9747),
    "fresno":          (36.7378, -119.7871),
    "sacramento":      (38.5816, -121.4944),
    "kansas city":     (39.0997,  -94.5786),
    "atlanta":         (33.7490,  -84.3880),
    "omaha":           (41.2565,  -95.9345),
    "colorado springs":(38.8339, -104.8214),
    "raleigh":         (35.7796,  -78.6382),
    "minneapolis":     (44.9778,  -93.2650),
    "tampa":           (27.9506,  -82.4572),
    "new orleans":     (29.9511,  -90.0715),
    "cleveland":       (41.4993,  -81.6944),
    "pittsburgh":      (40.4406,  -79.9959),
    "cincinnati":      (39.1031,  -84.5120),
    "detroit":         (42.3314,  -83.0458),
    "miami":           (25.7617,  -80.1918),
    "orlando":         (28.5383,  -81.3792),
    "buffalo":         (42.8864,  -78.8784),
    "richmond":        (37.5407,  -77.4360),
    "hartford":        (41.7658,  -72.6851),
    "providence":      (41.8240,  -71.4128),
    "salt lake city":  (40.7608, -111.8910),
    "birmingham":      (33.5186,  -86.8104),
    "anchorage":       (61.2181, -149.9003),
    "honolulu":        (21.3069, -157.8583),
    "st. louis":       (38.6270,  -90.1994),
    "saint louis":     (38.6270,  -90.1994),
    "st louis":        (38.6270,  -90.1994),
    "minneapolis":     (44.9778,  -93.2650),
    "st. paul":        (44.9537,  -93.0900),
    "rochester":       (43.1566,  -77.6088),
    "albany":          (42.6526,  -73.7562),
    "newark":          (40.7357,  -74.1724),
    "jersey city":     (40.7178,  -74.0431),
    "hartford":        (41.7658,  -72.6851),
    "springfield":     (42.1015,  -72.5898),
}

# ── sector keyword mapping ───────────────────────────────────────────────────
SECTOR_KEYWORDS = [
    ("Healthcare", [
        "nurse", "nursing", "rn ", " rn,", " lpn", "physician", "medical",
        "hospital", "health care", "healthcare", "clinical", "patient",
        "paramedic", "emt", "emergency medical", "dental", "pharmacy",
        "home care", "homecare", "social work", "social worker", "casework",
        "case worker", "mental health", "behavioral health", "therapist",
    ]),
    ("Education", [
        "teacher", "teaching", "educator", "school", "university", "college",
        "faculty", "academic", "professor", "instructional", "curriculum",
        "student", "classroom", "k-12", "k12", "district",
    ]),
    ("Logistics/Warehousing", [
        "warehouse", "logistics", "driver", "truck", "freight",
        "distribution", "transit", "transportation", "delivery",
        "supply chain", "port", "dock", "longshor",
    ]),
    ("Public Sector", [
        "public employee", "public sector", "government", "municipal",
        "city worker", "county worker", "state employee", "federal",
        "civil service", "public works", "public safety", "fire", "police",
        "corrections", "probation", "sanitation",
    ]),
    ("Building Trades", [
        "construction", "electrician", "plumber", "carpenter", "ironwork",
        "apprenticeship", "apprentice", "building trades", "trade union",
        "pipefitter", "sheet metal", "roofer", "painter", "laborer",
        "operating engineer", "boilermaker", "cement mason",
    ]),
    ("Manufacturing", [
        "manufacturing", "factory", "production", "assembly", "machinist",
        "auto worker", "steelwork", "textile", "food processing",
        "plant worker", "fabricat", "industrial",
    ]),
    ("Legal/Research", [
        "attorney", "lawyer", "legal", "paralegal", "counsel",
        "researcher", "research director", "policy analyst", "policy director",
        "analyst", "data analyst", "economist", "investigator",
    ]),
    ("Communications/Digital", [
        "communications", "digital", "media", "press", "journalist",
        "social media", "content", "designer", "web", "videographer",
        "photographer", "copywriter", "public relations", "pr director",
        "communications director", "graphic",
    ]),
    ("Finance/Admin", [
        "accountant", "accounting", "finance", "financial", "comptroller",
        "bookkeeper", "budget", "payroll", "audit", "treasurer",
        "administrator", "administrative", "office manager", "hr ",
        "human resources", "operations manager", "it director",
        "information technology", "database",
    ]),
]

# ── staff role keywords ──────────────────────────────────────────────────────
STAFF_KEYWORDS = [
    "organizer", "field organizer", "field director", "political director",
    "coordinator", "representative", "advocate", "lobbyist",
    "accountant", "attorney", "paralegal", "data director",
    "digital director", "it director", "researcher", "communications director",
    "press secretary", "field rep", "program director", "executive director",
    "associate director", "deputy director", "staff representative",
    "labor relations", "benefits administrator", "membership director",
    "organizing director", "campaign director", "strategic campaign",
]

# ── R2 sector-job keywords (high-SVS, rank-and-file) ─────────────────────────
R2_KEYWORDS = [
    "nurse", " rn ", " rn,", " lpn", "teacher", "educator",
    "driver", "warehouse worker", "logistics worker", "transit operator",
    "bus driver", "janitor", "custodian", "paramedic", "emt",
    "social worker", "caseworker", "public employee", "city worker",
    "county worker", "home care aide", "health aide", "food service",
]

# ── public sector sub-type keyword sets ──────────────────────────────────────
_PS_HEALTHCARE_KW = [
    "hospital", "health", "medical", "nurse", "nursing", "clinical",
    "patient", "pharmacy", "home care", "behavioral", "mental health",
]
_PS_EDUCATION_KW = [
    "school", "education", "teacher", "university", "college", "faculty",
    "academic", "professor", "district", "curriculum",
]
_PS_FEDERAL_KW = [
    "federal", "afge", "nffe", "nteu", "afscme federal", "u.s. ", "us ",
    "department of ", "dept. of ", "irs ", "va ", "postal",
]
_PS_STATE_KW = [
    "state employee", "state workers", "state worker",
    "afscme council", "state council", "commonwealth",
]


# ── helper functions ─────────────────────────────────────────────────────────

def text_for_match(record):
    """Combine title + org + description into a single lowercase string."""
    parts = [
        record.get("title") or "",
        record.get("organization") or "",
        record.get("description") or "",
    ]
    return " ".join(parts).lower()


def classify_public_sector_subtype(record):
    """
    Determine the specific Public Sector sub-type from org name and job title.
    Returns one of the four Public Sector label strings.
    """
    title = (record.get("title") or "").lower()
    org   = (record.get("organization") or "").lower()
    combined = title + " " + org

    if any(kw in combined for kw in _PS_HEALTHCARE_KW):
        return "Public Sector - Healthcare"
    if any(kw in combined for kw in _PS_EDUCATION_KW):
        return "Public Sector - Education"
    if any(kw in combined for kw in _PS_FEDERAL_KW):
        return "Public Sector - Federal"
    if any(kw in combined for kw in _PS_STATE_KW):
        return "Public Sector - State"
    return "Public Sector - Local Government"


def detect_sector_tags(record):
    """Return list of matching sector labels, primary first.
    Public Sector entries are resolved to their specific sub-type."""
    txt = text_for_match(record)
    matched = []
    for sector, keywords in SECTOR_KEYWORDS:
        for kw in keywords:
            if kw in txt:
                if sector == "Public Sector":
                    label = classify_public_sector_subtype(record)
                else:
                    label = sector
                if label not in matched:
                    matched.append(label)
                break
    return matched if matched else ["Other"]


def svs_score_for_tags(sector_tags):
    """Return SVS score based on highest-priority sector tag."""
    if not sector_tags:
        return 10
    return max(SVS_BY_SECTOR.get(s, 10) for s in sector_tags)


def classify_seniority(record):
    """
    Infer seniority level from job title keywords.
    Returns 'entry' | 'mid' | 'senior'.
    Entry keywords take precedence over senior keywords.
    Uses word-boundary matching to avoid substring false positives
    (e.g. "intern" must not match "internal").
    """
    title = (record.get("title") or "").lower()

    for kw in ENTRY_TITLE_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', title):
            return "entry"

    for kw in SENIOR_TITLE_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', title):
            return "senior"

    return "mid"


def classify_seiu_flag(record):
    """
    Returns True when org is SEIU at the international level (needs research note).
    Returns False for SEIU locals with explicit geographic identifiers.
    """
    org = (record.get("organization") or "").upper()
    if "SEIU" not in org:
        return False
    # Local with number: "SEIU Local 32BJ", "SEIU 1199", "SEIU-UHW", "SEIU Local 775"
    if re.search(r'SEIU[\s\-]+(LOCAL\s*\d+|\d+\w*|UHW|USWW|CTW|NHW|HCPA|775)', org):
        return False
    return True


def haversine(lat1, lon1, lat2, lon2):
    """Geodesic distance in miles between two lat/lon points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_job_coords(city, state_abbr):
    """
    Return (lat, lon) for a job location.
    Tries major city dict first, falls back to state centroid.
    Returns None if state is unknown.
    """
    if city:
        city_key = city.lower().strip()
        if city_key in MAJOR_CITY_COORDS:
            return MAJOR_CITY_COORDS[city_key]
    if state_abbr and state_abbr in STATE_CENTROIDS:
        return STATE_CENTROIDS[state_abbr]
    return None


def compute_distance_miles(record, user_lat, user_lon):
    """
    Compute geodesic distance in miles from job location to user home.
    Returns 0 for remote jobs, None if location is unparseable or user coords missing.
    """
    if user_lat is None or user_lon is None:
        return None

    loc_raw = (record.get("location_raw") or "").lower()
    if re.search(r'\bremote\b', loc_raw):
        return 0.0

    city = extract_city(record.get("location_raw"))
    state_abbr = record.get("state_abbr")
    job_coords = get_job_coords(city, state_abbr)

    if job_coords is None:
        return None

    return round(haversine(user_lat, user_lon, job_coords[0], job_coords[1]), 1)


def classify_role_type(record, svs_score):
    """Return (role_type, rf_subtype_label)."""
    if record.get("source") == "apprenticeship.gov":
        return "R3_apprenticeship", "Union Apprenticeship"

    txt = text_for_match(record)

    for kw in STAFF_KEYWORDS:
        if kw in txt:
            return "staff", None

    if svs_score >= 75:
        for kw in R2_KEYWORDS:
            if kw in txt:
                return "R2_career", "Career in Strategic Sector"
        if any(s in txt for s in ["hospital", "school district", "transit authority",
                                    "health system", "medical center", "health care",
                                    "healthcare system"]):
            return "R2_career", "Career in Strategic Sector"

    return "R4_union_job", "Good Union Job"


def extract_city(location_raw):
    """Extract city name from location string like 'Washington, DC'."""
    if not location_raw:
        return None
    loc = re.sub(r'\s*(remote|national|various|hybrid|multiple|anywhere)\s*$',
                 '', location_raw, flags=re.I).strip()
    if ',' in loc:
        city = loc.rsplit(',', 1)[0].strip()
        return city if city else None
    return loc.strip() or None


def build_msa_index(counties):
    """Build lookup: (state_abbr, city_token) → list of county records."""
    index = defaultdict(list)
    for c in counties:
        msa = c.get("msa_name")
        if not msa or msa == "Non-Metro":
            continue
        state = c.get("state", "")
        for token in re.split(r'[\s\-,]+', msa):
            if len(token) >= 4:
                index[(state, token.lower())].append(c)
    return index


def match_msa(city, state_abbr, msa_index, counties_by_state):
    """
    Try to match a city+state to an MSA name.
    Returns list of matching county records, or state-level fallback.
    """
    if not state_abbr:
        return []

    candidates = []
    if city:
        city_tokens = [t.lower() for t in re.split(r'\s+', city) if len(t) >= 4]
        for token in city_tokens:
            key = (state_abbr, token)
            if key in msa_index:
                candidates.extend(msa_index[key])

    seen = set()
    unique = []
    for c in candidates:
        if c["fips"] not in seen:
            seen.add(c["fips"])
            unique.append(c)

    if unique:
        return unique
    return counties_by_state.get(state_abbr, [])


def dominant_intervention(county_list):
    """Most common intervention type abbreviation among counties."""
    if not county_list:
        return "unknown"
    counts = Counter(
        INTERVENTION_MAP.get(c.get("intervention_type", ""), "unknown")
        for c in county_list
    )
    return counts.most_common(1)[0][0]


def _role_match_component(role_type):
    """Normalized 0–1 role alignment score."""
    return {
        "staff":            0.90,
        "R3_apprenticeship": 0.85,
        "R2_career":         0.75,
        "R4_union_job":      0.55,
    }.get(role_type, 0.55)


def compute_impact_score(svs_score, distance_miles, role_type, oos_score,
                          is_swing_state, is_mcalevey_priority, user_profile):
    """
    Profile-weighted impact score.

    Components (each normalized 0–1, then scaled by profile weights to 0–100):
      svs_component:        strategic sector value
      distance_component:   proximity (closer = better; remote = perfect)
      role_match_component: role type alignment with user path
      sector_component:     local organizing opportunity (OOS terrain)

    Flat bonuses added after weighting:
      +8 if swing state
      +10 if McAlevey priority (strategic R2/R3)
    """
    profile = USER_PROFILES.get(
        (user_profile or {}).get("type", "entry_relocate"),
        USER_PROFILES["entry_relocate"],
    )

    svs_component = svs_score / 100.0

    if distance_miles is None:
        distance_component = 0.5  # neutral when unknown
    elif distance_miles == 0:
        distance_component = 1.0
    else:
        distance_component = max(0.0, 1.0 - distance_miles / 2500.0)

    role_component = _role_match_component(role_type)

    sector_component = (oos_score / 100.0) if oos_score is not None else 0.5

    score = (
        profile["svs_weight"]        * svs_component +
        profile["distance_weight"]   * distance_component +
        profile["role_match_weight"] * role_component +
        profile["sector_weight"]     * sector_component
    ) * 100.0

    if is_swing_state:
        score += SWING_STATE_BONUS
    if is_mcalevey_priority:
        score += 10

    return min(round(score, 2), 100)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading data...")
    with open(UNIONJOBS_RAW) as f:
        raw_listings = json.load(f)
    with open(COUNTY_SCORES) as f:
        counties = json.load(f)

    print(f"  {len(raw_listings)} unionjobs.com listings")
    print(f"  {len(counties)} counties")

    user_profile = DEFAULT_USER_PROFILE
    user_lat = user_profile.get("home_lat")
    user_lon = user_profile.get("home_lon")

    msa_index = build_msa_index(counties)
    counties_by_state = defaultdict(list)
    for c in counties:
        counties_by_state[c["state"]].append(c)

    listings = []
    for raw in raw_listings:
        rec = dict(raw)

        # sector_tags (public sector now resolves to specific sub-type)
        sector_tags = detect_sector_tags(rec)
        rec["sector_tags"] = sector_tags

        # SVS score
        svs_score = svs_score_for_tags(sector_tags)
        rec["svs_score"] = svs_score

        # role_type
        role_type, rf_subtype_label = classify_role_type(rec, svs_score)
        rec["role_type"] = role_type
        rec["rf_subtype_label"] = rf_subtype_label

        # seniority (new)
        seniority_level = classify_seniority(rec)
        rec["seniority_level"] = seniority_level

        # McAlevey priority
        rec["is_mcalevey_priority"] = (
            svs_score >= 75 and role_type in ("R2_career", "R3_apprenticeship")
        )

        # location normalization
        state_abbr = rec.get("state_abbr")
        city = extract_city(rec.get("location_raw"))
        rec["is_swing_state"] = state_abbr in SWING_STATES if state_abbr else False

        matched_counties = match_msa(city, state_abbr, msa_index, counties_by_state)

        if matched_counties and matched_counties[0].get("msa_name") not in (None, "Non-Metro"):
            rec["msa_name"] = matched_counties[0]["msa_name"]
        elif state_abbr:
            rec["msa_name"] = state_abbr
        else:
            rec["msa_name"] = None

        # terrain matching
        if matched_counties and matched_counties[0].get("msa_name") not in (None, "Non-Metro"):
            oos_scores = [c["organizing_opportunity_score"] for c in matched_counties
                          if c.get("organizing_opportunity_score") is not None]
            rec["oos_score"] = round(max(oos_scores), 2) if oos_scores else None
            rec["intervention_type"] = dominant_intervention(matched_counties)
        else:
            rec["oos_score"] = None
            rec["intervention_type"] = "unknown"

        # distance (new)
        distance_miles = compute_distance_miles(rec, user_lat, user_lon)
        rec["distance_miles"] = distance_miles

        # impact_score (profile-weighted)
        rec["impact_score"] = compute_impact_score(
            svs_score, distance_miles, role_type,
            rec["oos_score"], rec["is_swing_state"],
            rec["is_mcalevey_priority"], user_profile,
        )

        # SEIU footnote flag (new)
        needs_research_note = classify_seiu_flag(rec)
        rec["needs_research_note"] = needs_research_note

        # entry-level triage flag (new)
        rec["is_entry_level"] = (seniority_level == "entry")

        listings.append({
            "job_id":               rec["job_id"],
            "title":                rec.get("title"),
            "organization":         rec.get("organization"),
            "location_raw":         rec.get("location_raw"),
            "state_abbr":           rec.get("state_abbr"),
            "msa_name":             rec.get("msa_name"),
            "date_posted":          rec.get("date_posted"),
            "salary_raw":           rec.get("salary"),
            "description":          rec.get("description"),
            "apply_url":            rec.get("apply_url"),
            "source":               rec.get("source"),
            "role_type":            rec["role_type"],
            "rf_subtype_label":     rec["rf_subtype_label"],
            "sector_tags":          rec["sector_tags"],
            "svs_score":            rec["svs_score"],
            "intervention_type":    rec["intervention_type"],
            "impact_score":         rec["impact_score"],
            "oos_score":            rec["oos_score"],
            "is_swing_state":       rec["is_swing_state"],
            "is_mcalevey_priority": rec["is_mcalevey_priority"],
            # new fields
            "seniority_level":      rec["seniority_level"],
            "is_entry_level":       rec["is_entry_level"],
            "needs_research_note":  rec["needs_research_note"],
            "distance_miles":       rec["distance_miles"],
        })

    output = {
        "last_scraped": datetime.now(timezone.utc).isoformat(),
        "total_listings": len(listings),
        "source_status": {
            "unionjobs.com": "ok",
            "apprenticeship.gov": "pending — token requested, will be added in follow-up session",
        },
        "listings": listings,
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nOutput written to {OUTPUT_PATH}")

    # ── reporting ────────────────────────────────────────────────────────────
    role_counts     = Counter(l["role_type"] for l in listings)
    sector_counts   = Counter(t for l in listings for t in l["sector_tags"])
    priority_count  = sum(1 for l in listings if l["is_mcalevey_priority"])
    entry_count     = sum(1 for l in listings if l["is_entry_level"])
    senior_count    = sum(1 for l in listings if l["seniority_level"] == "senior")
    seiu_flag_count = sum(1 for l in listings if l["needs_research_note"])

    print("\n── Role type distribution ──")
    for role, count in sorted(role_counts.items(), key=lambda x: -x[1]):
        print(f"  {role:<25} {count:>4}")

    print("\n── Sector tag distribution (top 10) ──")
    for sector, count in sector_counts.most_common(10):
        print(f"  {sector:<38} {count:>4}")

    print(f"\n── Seniority ──")
    print(f"  entry:  {entry_count}")
    print(f"  senior: {senior_count}")
    print(f"  mid:    {len(listings) - entry_count - senior_count}")

    print(f"\n── McAlevey priority ──")
    print(f"  is_mcalevey_priority=True:  {priority_count}/{len(listings)}")

    print(f"\n── SEIU footnote flag ──")
    print(f"  needs_research_note=True:  {seiu_flag_count}/{len(listings)}")

    print("\n── Top 5 by impact_score ──")
    top5 = sorted(listings, key=lambda x: -x["impact_score"])[:5]
    for l in top5:
        print(f"  impact={l['impact_score']:5.1f}  role={l['role_type']:<20}  "
              f"svs={l['svs_score']:>3}  seniority={l['seniority_level']:<6}  "
              f"int={l['intervention_type']}  msa={l['msa_name'] or 'n/a'}")
        print(f"    title: {(l['title'] or '')[:60]}")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
