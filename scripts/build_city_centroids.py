#!/usr/bin/env python3
"""
Build output/city_centroids.json — top 5,000 US cities by population.

Data source: GeoNames cities1000 dataset (cities/places with population >= 1000)
  URL: https://download.geonames.org/export/dump/cities1000.zip
  License: Creative Commons Attribution 4.0 International
  Attribution: GeoNames (https://www.geonames.org)

Note on Census approach: Census 2020 Gazetteer provides good lat/lng but the
Census ACS population API (api.census.gov) now requires a registration key,
making a fully public-domain pipeline impractical without one.
GeoNames provides equivalent quality data under CC-BY 4.0.
"""

import io
import json
import zipfile

import requests

GEONAMES_URL = "https://download.geonames.org/export/dump/cities1000.zip"
OUT_PATH = "output/city_centroids.json"
TOP_N = 5000

# GeoNames TSV column indices (0-based)
COL_NAME = 1
COL_LAT = 4
COL_LNG = 5
COL_FEAT_CLASS = 6   # 'P' = populated place
COL_FEAT_CODE = 7
COL_COUNTRY = 8
COL_ADMIN1 = 10      # state abbreviation for US entries
COL_POP = 14

# Skip sub-city sections (neighborhoods, quarters) — they duplicate
# population across their parent city and have wrong centroids for job search
SKIP_FEAT_CODES = {"PPLX", "PPLCH", "PPLQ", "PPLW"}


def download_and_parse() -> list[dict]:
    print("Downloading GeoNames cities1000.zip...", flush=True)
    r = requests.get(GEONAMES_URL, timeout=120)
    r.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    text = zf.read("cities1000.txt").decode("utf-8")

    places = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 15:
            continue
        if parts[COL_COUNTRY] != "US":
            continue
        if parts[COL_FEAT_CODE] in SKIP_FEAT_CODES:
            continue
        try:
            pop = int(parts[COL_POP])
            lat = round(float(parts[COL_LAT]), 4)
            lng = round(float(parts[COL_LNG]), 4)
        except ValueError:
            continue
        if pop <= 0:
            continue
        places.append(
            {
                "city": parts[COL_NAME],
                "state": parts[COL_ADMIN1],
                "lat": lat,
                "lng": lng,
                "pop": pop,
            }
        )

    return places


def main():
    places = download_and_parse()
    print(f"Parsed: {len(places):,} US places (population > 0, excl. PPLX/historic)", flush=True)

    places.sort(key=lambda x: x["pop"], reverse=True)
    results = places[:TOP_N]

    # Drop population from output — sort order is baked in, frontend doesn't need it
    output = [{"city": p["city"], "state": p["state"], "lat": p["lat"], "lng": p["lng"]} for p in results]

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, separators=(",", ":"))

    size_kb = len(open(OUT_PATH, "rb").read()) / 1024
    print(f"\nOutput: {len(results):,} entries, {size_kb:.1f} KB → {OUT_PATH}")

    # Spot-checks
    targets = [("Berkeley", "CA"), ("Madison", "WI"), ("Cheyenne", "WY")]
    for city_name, state in targets:
        match = next(
            (r for r in results if r["city"] == city_name and r["state"] == state),
            None,
        )
        if match:
            idx = results.index(match) + 1
            print(
                f"  {city_name}, {state}: lat={match['lat']}, lng={match['lng']}, "
                f"pop={match['pop']:,} (rank #{idx})"
            )
        else:
            print(f"  {city_name}, {state}: NOT FOUND")


if __name__ == "__main__":
    main()
