"""
Ingest Census Bureau 118th Congress district-to-county relationship file.

Source: https://www2.census.gov/geo/docs/maps-data/data/rel2020/cd-sld/tab20_cd11820_county20_natl.txt
  NOTE: File lives at rel2020/cd-sld/ — NOT rel2020/cd118/ (that path 404s).
Vintage: 2020 Census geographies, 118th Congress boundaries

Output: data/processed/district_county_crosswalk.csv
Columns:
  district_geoid   - 4-digit GEOID (2-digit state FIPS + 2-digit district number)
  district_state   - 2-digit state FIPS
  district_number  - 2-digit district number (00 = at-large)
  county_fips      - 5-digit county FIPS
  overlap_weight   - AREALAND_PART / AREALAND_CD118_20
                     (fraction of the district's land area that falls in this county)

Used by: scoring/p1_congressional.py (Phase 3)
  - To score a county, average P1 scores of all districts overlapping it,
    weighted by county's share of each district (overlap_weight).
"""

import csv
import sys
from pathlib import Path

RAW_FILE = Path("data/raw/census_cd_county_rel.txt")
OUT_FILE = Path("data/processed/district_county_crosswalk.csv")


def parse_and_write():
    rows_written = 0
    skipped_zero_area = 0
    skipped_bad_area = 0

    with open(RAW_FILE, encoding="utf-8-sig") as infile, \
         open(OUT_FILE, "w", newline="") as outfile:

        reader = csv.DictReader(infile, delimiter="|")
        writer = csv.DictWriter(outfile, fieldnames=[
            "district_geoid", "district_state", "district_number",
            "county_fips", "overlap_weight"
        ])
        writer.writeheader()

        for row in reader:
            district_geoid = row["GEOID_CD118_20"].strip().zfill(4)
            county_fips = row["GEOID_COUNTY_20"].strip().zfill(5)

            try:
                arealand_part = float(row["AREALAND_PART"])
                arealand_district = float(row["AREALAND_CD118_20"])
            except (ValueError, KeyError):
                skipped_bad_area += 1
                continue

            if arealand_district <= 0:
                # At-large or non-voting district with no land (e.g., DC, PR)
                skipped_zero_area += 1
                continue

            overlap_weight = arealand_part / arealand_district

            writer.writerow({
                "district_geoid": district_geoid,
                "district_state": district_geoid[:2],
                "district_number": district_geoid[2:],
                "county_fips": county_fips,
                "overlap_weight": round(overlap_weight, 6),
            })
            rows_written += 1

    return rows_written, skipped_zero_area, skipped_bad_area


def validate(county_scores_path="data/county_scores.json"):
    import json

    with open(OUT_FILE) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total_rows = len(rows)
    print(f"Total crosswalk rows: {total_rows}")

    # Overlap weights per district should sum to ~1.0
    from collections import defaultdict
    district_weights = defaultdict(float)
    county_districts = defaultdict(list)

    for r in rows:
        district_weights[r["district_geoid"]] += float(r["overlap_weight"])
        county_districts[r["county_fips"]].append(r["district_geoid"])

    # Check a known multi-district county: Los Angeles (06037)
    la_districts = county_districts.get("06037", [])
    print(f"\nLos Angeles County (06037) overlaps districts: {sorted(set(la_districts))}")

    # Check a district that spans multiple counties: sum of weights
    sample_district = "0602"  # CA-02
    district_rows = [r for r in rows if r["district_geoid"] == sample_district]
    weight_sum = sum(float(r["overlap_weight"]) for r in district_rows)
    print(f"\nDistrict {sample_district} spans {len(district_rows)} counties, weight sum: {weight_sum:.4f}")

    # Districts where weights deviate significantly from 1.0
    bad_districts = {d: w for d, w in district_weights.items() if abs(w - 1.0) > 0.05}
    if bad_districts:
        print(f"\nWARNING: {len(bad_districts)} districts with weights not summing to ~1.0:")
        for d, w in sorted(bad_districts.items())[:5]:
            print(f"  {d}: {w:.4f}")
    else:
        print(f"\nAll {len(district_weights)} districts have weights summing within 5% of 1.0")

    # Check coverage against county_scores.json
    try:
        with open(county_scores_path) as f:
            county_scores = json.load(f)
        score_fips = {r["fips"] for r in county_scores}
        crosswalk_fips = {r["county_fips"] for r in rows}
        missing = score_fips - crosswalk_fips
        print(f"\nFIPS in county_scores.json: {len(score_fips)}")
        print(f"FIPS in crosswalk: {len(crosswalk_fips)}")
        if missing:
            print(f"FIPS missing from crosswalk ({len(missing)}): {sorted(missing)[:10]}")
        else:
            print("All county_scores FIPS appear in crosswalk")
    except FileNotFoundError:
        print("\ncounty_scores.json not found — skipping coverage check")


if __name__ == "__main__":
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print(f"Reading: {RAW_FILE}")
    rows_written, skipped_zero, skipped_bad = parse_and_write()
    print(f"Written: {OUT_FILE}")
    print(f"  Rows written:     {rows_written}")
    print(f"  Skipped (zero area): {skipped_zero}")
    print(f"  Skipped (bad data):  {skipped_bad}")

    validate()
