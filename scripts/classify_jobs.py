#!/usr/bin/env python3
"""
Task 3: Classify and unify job listings into jobs_data.json.
Inputs:  output/unionjobs_raw.json, data/county_scores.json
Output:  output/jobs_data.json
"""

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIONJOBS_RAW  = os.path.join(ROOT, "output", "unionjobs_raw.json")
COUNTY_SCORES  = os.path.join(ROOT, "data",   "county_scores.json")
OUTPUT_PATH    = os.path.join(ROOT, "output", "jobs_data.json")

# ── constants ────────────────────────────────────────────────────────────────
SWING_STATES = {"PA", "WI", "MI", "AZ", "GA", "NV", "NC"}

SVS_BY_SECTOR = {
    "Healthcare":           100,
    "Education":            100,
    "Public Sector":        100,
    "Logistics/Warehousing": 75,
    "Building Trades":       50,
    "Manufacturing":         25,
    "Legal/Research":        10,
    "Communications/Digital":10,
    "Finance/Admin":         10,
    "Other":                 10,
}

INTERVENTION_MAP = {
    "Type A: Organize Unorganized": "A",
    "Type B: Political Activation":  "B",
    "Type C: Partnership":           "C",
}

# ── sector keyword mapping ───────────────────────────────────────────────────
# Each entry: (sector_label, [keywords])
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


# ── helper functions ─────────────────────────────────────────────────────────

def text_for_match(record):
    """Combine title + description into a single lowercase string for keyword matching."""
    parts = [
        record.get("title") or "",
        record.get("organization") or "",
        record.get("description") or "",
    ]
    return " ".join(parts).lower()


def detect_sector_tags(record):
    """Return list of matching sector labels, primary first."""
    txt = text_for_match(record)
    matched = []
    for sector, keywords in SECTOR_KEYWORDS:
        for kw in keywords:
            if kw in txt:
                if sector not in matched:
                    matched.append(sector)
                break
    return matched if matched else ["Other"]


def svs_score_for_tags(sector_tags):
    """Return SVS score based on highest-priority sector tag."""
    if not sector_tags:
        return 10
    return max(SVS_BY_SECTOR.get(s, 10) for s in sector_tags)


def classify_role_type(record, svs_score):
    """Return (role_type, rf_subtype_label)."""
    if record.get("source") == "apprenticeship.gov":
        return "R3_apprenticeship", "Union Apprenticeship"

    txt = text_for_match(record)

    # Staff detection
    for kw in STAFF_KEYWORDS:
        if kw in txt:
            return "staff", None

    # R2: rank-and-file in high-SVS sector
    if svs_score >= 75:
        for kw in R2_KEYWORDS:
            if kw in txt:
                return "R2_career", "Career in Strategic Sector"
        # Also classify as R2 if the title/org is clearly a sector job
        # (e.g. a hospital listing, school district listing)
        if any(s in txt for s in ["hospital", "school district", "transit authority",
                                    "health system", "medical center", "health care",
                                    "healthcare system"]):
            return "R2_career", "Career in Strategic Sector"

    # R4: union job in lower-SVS sector
    return "R4_union_job", "Good Union Job"


def extract_city(location_raw):
    """Extract city name from location string like 'Washington, DC' or 'Los Angeles, CA'."""
    if not location_raw:
        return None
    # Strip common suffixes
    loc = re.sub(r'\s*(remote|national|various|hybrid|multiple|anywhere)\s*$',
                 '', location_raw, flags=re.I).strip()
    # Extract part before last comma (the city)
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
        # Index by each word in the MSA name (≥4 chars) + state
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
        # Try multi-word city matching (e.g. "Los Angeles" → tokens "los", "angeles")
        city_tokens = [t.lower() for t in re.split(r'\s+', city) if len(t) >= 4]
        for token in city_tokens:
            key = (state_abbr, token)
            if key in msa_index:
                candidates.extend(msa_index[key])

    # Deduplicate by FIPS
    seen = set()
    unique = []
    for c in candidates:
        if c["fips"] not in seen:
            seen.add(c["fips"])
            unique.append(c)

    if unique:
        return unique

    # Fallback: return all counties in the state (for state-level msa_name)
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


def compute_impact_score(oos_score, is_swing_state, is_mcalevey_priority, role_type):
    base = oos_score if oos_score is not None else 50
    score = base
    if is_swing_state:
        score += 15
    if is_mcalevey_priority:
        score += 10
    if role_type == "R3_apprenticeship" and is_mcalevey_priority:
        score += 5
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

    # Build lookup structures
    msa_index = build_msa_index(counties)
    counties_by_state = defaultdict(list)
    for c in counties:
        counties_by_state[c["state"]].append(c)

    # STEP 1–7: classify every listing
    listings = []
    for raw in raw_listings:
        rec = dict(raw)  # shallow copy

        # STEP 3 — sector_tags
        sector_tags = detect_sector_tags(rec)
        rec["sector_tags"] = sector_tags

        # STEP 4 — SVS score
        svs_score = svs_score_for_tags(sector_tags)
        rec["svs_score"] = svs_score

        # STEP 5 — role_type
        role_type, rf_subtype_label = classify_role_type(rec, svs_score)
        rec["role_type"] = role_type
        rec["rf_subtype_label"] = rf_subtype_label

        # McAlevey priority: strategic sector AND rank-and-file path only
        rec["is_mcalevey_priority"] = (
            svs_score >= 75 and role_type in ("R2_career", "R3_apprenticeship")
        )

        # STEP 2 — location normalization
        state_abbr = rec.get("state_abbr")
        city = extract_city(rec.get("location_raw"))
        rec["is_swing_state"] = state_abbr in SWING_STATES if state_abbr else False

        matched_counties = match_msa(city, state_abbr, msa_index, counties_by_state)

        if matched_counties and matched_counties[0].get("msa_name") not in (None, "Non-Metro"):
            rec["msa_name"] = matched_counties[0]["msa_name"]
        elif state_abbr:
            # Use state name as fallback msa_name
            state_names = {c["state"]: c.get("region", state_abbr)
                           for c in counties if c["state"] == state_abbr}
            rec["msa_name"] = state_abbr  # two-letter abbr as fallback
        else:
            rec["msa_name"] = None

        # STEP 6 — terrain matching
        if matched_counties and matched_counties[0].get("msa_name") not in (None, "Non-Metro"):
            oos_scores = [c["organizing_opportunity_score"] for c in matched_counties
                          if c.get("organizing_opportunity_score") is not None]
            rec["oos_score"] = round(max(oos_scores), 2) if oos_scores else None
            rec["intervention_type"] = dominant_intervention(matched_counties)
        else:
            rec["oos_score"] = None
            rec["intervention_type"] = "unknown"

        # STEP 7 — impact_score
        rec["impact_score"] = compute_impact_score(
            rec["oos_score"], rec["is_swing_state"],
            rec["is_mcalevey_priority"], role_type
        )

        # Enforce unified schema field order
        listings.append({
            "job_id":           rec["job_id"],
            "title":            rec.get("title"),
            "organization":     rec.get("organization"),
            "location_raw":     rec.get("location_raw"),
            "state_abbr":       rec.get("state_abbr"),
            "msa_name":         rec.get("msa_name"),
            "date_posted":      rec.get("date_posted"),
            "salary_raw":       rec.get("salary"),
            "description":      rec.get("description"),
            "apply_url":        rec.get("apply_url"),
            "source":           rec.get("source"),
            "role_type":        rec["role_type"],
            "rf_subtype_label": rec["rf_subtype_label"],
            "sector_tags":      rec["sector_tags"],
            "svs_score":        rec["svs_score"],
            "intervention_type":rec["intervention_type"],
            "impact_score":     rec["impact_score"],
            "oos_score":        rec["oos_score"],
            "is_swing_state":   rec["is_swing_state"],
            "is_mcalevey_priority": rec["is_mcalevey_priority"],
        })

    # Write output
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
    role_counts = Counter(l["role_type"] for l in listings)
    sector_counts = Counter(t for l in listings for t in l["sector_tags"])
    priority_count = sum(1 for l in listings if l["is_mcalevey_priority"])

    print("\n── Role type distribution ──")
    for role, count in sorted(role_counts.items(), key=lambda x: -x[1]):
        print(f"  {role:<25} {count:>4}")

    print("\n── Sector tag distribution (top 10) ──")
    for sector, count in sector_counts.most_common(10):
        print(f"  {sector:<30} {count:>4}")

    print(f"\n── McAlevey priority ──")
    print(f"  is_mcalevey_priority=True:  {priority_count}/{len(listings)}")
    print(f"  is_mcalevey_priority=False: {len(listings)-priority_count}/{len(listings)}")

    print("\n── Top 5 by impact_score ──")
    top5 = sorted(listings, key=lambda x: -x["impact_score"])[:5]
    for l in top5:
        print(f"  impact={l['impact_score']:5.1f}  role={l['role_type']:<20}  "
              f"svs={l['svs_score']:>3}  int={l['intervention_type']}  "
              f"msa={l['msa_name'] or 'n/a'}")
        print(f"    title: {(l['title'] or '')[:60]}")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
