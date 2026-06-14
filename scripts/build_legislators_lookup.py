"""
Terrain v2.0 — County Legislators Lookup Builder
Builds data/processed/county_legislators_lookup.json

A pre-computed file mapping county FIPS → list of current legislators
with their P2 scores, party, chamber, district, and key vote scores.

Sources:
  data/processed/federal_p2_combined.csv  (federal legislators)
  data/processed/district_county_crosswalk.csv  (House district → county)
  data/county_scores_v2_test.json  (county list with state info)

Run: python scripts/build_legislators_lookup.py
Updated monthly by: .github/workflows/refresh_legislators.yml

Output format:
{
  "generated": "ISO timestamp",
  "counties": {
    "42101": {
      "federal": [
        {
          "bioguide_id": "C000174",
          "name": "Bob Casey",
          "party": "D",
          "chamber": "senate",
          "district": null,
          "title": "Senator",
          "p2_combined": 0.95,
          "key_vote_score": 1.0,
          "state": "PA"
        },
        ...
      ],
      "state": []  // populated after Agent E completes
    }
  }
}
"""
import csv
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

REPO_ROOT = Path(__file__).parent.parent


def load_county_states():
    """Load FIPS → state mapping from county_scores_v2_test.json."""
    path = REPO_ROOT / "data" / "county_scores_v2_test.json"
    with open(path) as f:
        data = json.load(f)
    counties = data.get("counties", data) if isinstance(data, dict) else data
    return {
        str(c.get("fips", "")).zfill(5): c.get("state", "")
        for c in counties
    }


def load_federal_legislators():
    """Load federal P2 scores from federal_p2_combined.csv."""
    path = REPO_ROOT / "data" / "processed" / "federal_p2_combined.csv"
    legislators = []
    with open(path) as f:
        for row in csv.DictReader(f):
            legislators.append({
                "bioguide_id": row.get("bioguide_id", ""),
                "name": row.get("name", ""),
                "party": row.get("party", ""),
                "chamber": row.get("chamber", ""),
                "state": row.get("state", ""),
                "district": row.get("district", "") or None,
                "p2_combined": float(row["p2_combined"]) if row.get("p2_combined") else None,
                "key_vote_score": float(row["key_vote_score"]) if row.get("key_vote_score") else None,
                "coverage_type": row.get("coverage_type", "")
            })
    return legislators


def load_crosswalk():
    """Load district → county overlap weights."""
    path = REPO_ROOT / "data" / "processed" / "district_county_crosswalk.csv"
    crosswalk = defaultdict(list)
    with open(path) as f:
        for row in csv.DictReader(f):
            geoid = row.get("district_geoid", "")
            fips = str(row.get("county_fips", "")).zfill(5)
            weight = float(row.get("overlap_weight", 0))
            if geoid and fips and weight > 0:
                crosswalk[geoid].append((fips, weight))
    return crosswalk


STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "FL": "12", "GA": "13", "HI": "15", "ID": "16",
    "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22",
    "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40",
    "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47",
    "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54",
    "WI": "55", "WY": "56", "DC": "11"
}

AT_LARGE_STATES = {"AK", "DE", "MT", "ND", "SD", "VT", "WY"}


def build_lookup():
    county_states = load_county_states()
    legislators = load_federal_legislators()
    crosswalk = load_crosswalk()

    output = {fips: {"federal": [], "state": []} for fips in county_states}

    # Assign senators to all counties in their state
    for leg in legislators:
        if leg["chamber"] != "senate":
            continue
        state = leg["state"]
        entry = {
            "bioguide_id": leg["bioguide_id"],
            "name": leg["name"],
            "party": leg["party"],
            "chamber": "senate",
            "district": None,
            "title": "Senator",
            "p2_combined": leg["p2_combined"],
            "key_vote_score": leg["key_vote_score"],
            "state": state
        }
        for fips, s in county_states.items():
            if s == state:
                output[fips]["federal"].append(entry)

    # Assign House members via crosswalk
    for leg in legislators:
        if leg["chamber"] != "house":
            continue
        state = leg["state"]
        district = str(leg["district"] or "00").zfill(2)
        state_fips = STATE_FIPS.get(state, "")
        if not state_fips:
            continue
        geoid = state_fips + district
        counties_for_district = crosswalk.get(geoid, [])
        if not counties_for_district and state in AT_LARGE_STATES:
            counties_for_district = [
                (fips, 1.0)
                for fips, s in county_states.items()
                if s == state
            ]
        entry = {
            "bioguide_id": leg["bioguide_id"],
            "name": leg["name"],
            "party": leg["party"],
            "chamber": "house",
            "district": district,
            "title": f"Rep. (District {int(district)})" if district != "00" else "Rep. (At-Large)",
            "p2_combined": leg["p2_combined"],
            "key_vote_score": leg["key_vote_score"],
            "state": state
        }
        for fips, weight in counties_for_district:
            if fips in output:
                output[fips]["federal"].append(entry)

    # Sort: senators first, then House by P2 descending
    for fips in output:
        output[fips]["federal"].sort(
            key=lambda x: (0 if x["chamber"] == "senate" else 1, -(x["p2_combined"] or 0))
        )

    result = {
        "generated": datetime.now().isoformat(),
        "_note": "Federal legislators per county. State legislators pending Agent E completion.",
        "_source": "federal_p2_combined.csv + district_county_crosswalk.csv",
        "counties": output
    }

    out_path = REPO_ROOT / "data" / "processed" / "county_legislators_lookup.json"
    with open(out_path, "w") as f:
        json.dump(result, f)

    covered = sum(1 for v in output.values() if v["federal"])
    print(f"Written: {out_path}")
    print(f"Counties with federal legislators: {covered}/{len(output)}")


if __name__ == "__main__":
    build_lookup()
