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

# Leadership (0.7): senior/sr. prefix, director titles, supervisors, lead-X patterns
_LEAD_MOD_RE = re.compile(
    r'\b(senior|\bsr\.?\b'
    r'|lead\s+(?:counsel|researcher|analyst|representative|attorney|coordinator)'
    r'|(?:deputy\s+)?director(?!\s+of\b)'
    r'|supervisor|business\s+agent'
    r')\b',
    re.IGNORECASE,
)

# Early-career (0.9): interns, fellows, clerks, explicit entry markers
_EARLY_STRONG_RE = re.compile(
    r'\b(intern(?:ship)?s?|fellow(?:ship)?s?|apprentice(?:ship)?s?'
    r'|entry[\s-]level|junior'
    r'|organizers?[\s-]in[\s-]training'
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

    # Temporary roles are entry-level regardless of title seniority signals
    if _TEMP_RE.search(title):
        return "early-career", 0.7

    # "Executive Administrative/Program Assistant" is experienced support staff, not early-career
    if _EXEC_ADMIN_ASSISTANT_RE.search(title):
        return "experienced", 0.5

    # Strong leadership (0.9): C-suite, VP, ED, Director of X, President
    if _LEAD_STRONG_RE.search(title):
        return "leadership", 0.9

    # Strong early-career (0.9): interns, fellows, clerks, explicit entry markers
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

# Communications: press, media, messaging, creative
_COMM_KW_RE = re.compile(
    r'\b(communications\s+(?:director|specialist|coordinator|manager|staff)'
    r'|press\s+(?:secretary|director)|media\s+(?:director|relations|strategist)'
    r'|messaging|digital\s+(?:director|strategist|organizer)'
    r'|creative\s+director|public\s+relations|graphic\s+designer'
    r'|content\s+(?:director|manager|strategist)|social\s+media'
    r'|marketing\s+(?:director|manager)|communications\b)\b',
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


def classify_location_parsed(job: dict) -> dict:
    city = job.get("city") or None
    state = job.get("state_abbr") or None
    raw = job.get("location_raw") or ""

    region: Optional[str] = None
    if city:
        region = CITY_REGION_MAP.get(city)
    if region is None and state:
        region = STATE_REGION_MAP.get(state)

    near_airports: List[str] = []
    if city:
        near_airports = CITY_AIRPORT_MAP.get(city, [])

    return {
        "city": city,
        "state": state,
        "region": region,
        "near_airports": near_airports,
        "raw": raw,
    }


# ---------------------------------------------------------------------------
# Main enrichment function
# ---------------------------------------------------------------------------
def enrich_job(job: dict) -> dict:
    level, confidence = classify_experience(job)
    return {
        **job,
        "experience_level":      level,
        "experience_confidence": confidence,
        "job_function":          classify_job_function(job),
        "location_type":         classify_location_type(job),
        "location_parsed":       classify_location_parsed(job),
        "seniority_signals":     extract_seniority_signals(job),
    }


# ---------------------------------------------------------------------------
# Accuracy comparison
# Maps old 4-bucket ground truth (entry/mid/senior/executive) → new 3-bucket
# ---------------------------------------------------------------------------
COMPARE_FIELDS = ["experience_level", "job_function", "location_type"]

_EXP_REMAP = {
    "entry":     "early-career",
    "mid":       "experienced",
    "senior":    "leadership",
    "executive": "leadership",
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
            # Remap old experience_level values to new 3-bucket schema
            if field == "experience_level":
                gt_val = _EXP_REMAP.get(gt_val, gt_val)
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


def main():
    parser = argparse.ArgumentParser(description="Enrich jobs with deterministic rules")
    parser.add_argument("--input",   default="data/classified_jobs.json")
    parser.add_argument("--output",  default="data/classified_jobs.json")
    parser.add_argument("--compare", default=None, help="Path to enriched_jobs.json for accuracy check")
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


if __name__ == "__main__":
    main()
