"""
Ingest GovTrack ideology scores and compute combined federal P2 scores.

Data sources:
  - data/raw/legislators_current.yaml  (unitedstates/congress-legislators)
  - data/raw/govtrack_sponsorship_s_119.txt  (GovTrack Senate, 119th Congress)
  - data/raw/govtrack_sponsorship_h_119.txt  (GovTrack House, 119th Congress)

Crosswalk logic:
  - Senate member_id = LIS ID (e.g. "S383") → yaml id.lis → yaml id.govtrack
  - House  member_id = bioguide ID             → yaml id.bioguide → yaml id.govtrack

Output:
  - data/processed/federal_ideology_scores.csv
  - data/processed/federal_p2_combined.csv
"""

import csv
import yaml

RAW_YAML   = "data/raw/legislators_current.yaml"
RAW_S_TXT  = "data/raw/govtrack_sponsorship_s_119.txt"
RAW_H_TXT  = "data/raw/govtrack_sponsorship_h_119.txt"
KV_SCORES  = "data/processed/federal_key_vote_scores.csv"

OUT_IDEOLOGY = "data/processed/federal_ideology_scores.csv"
OUT_COMBINED = "data/processed/federal_p2_combined.csv"

KEY_VOTE_WEIGHT = 0.60
IDEOLOGY_WEIGHT = 0.40


def build_crosswalk(yaml_path):
    """Return (lis_to_govtrack, bioguide_to_govtrack) dicts from legislators YAML."""
    with open(yaml_path) as f:
        legislators = yaml.safe_load(f)

    lis_to_govtrack = {}
    bioguide_to_govtrack = {}

    for leg in legislators:
        ids = leg.get("id", {})
        govtrack_id = ids.get("govtrack")
        if not govtrack_id:
            continue
        govtrack_id = int(govtrack_id)

        lis = ids.get("lis")
        if lis:
            lis_to_govtrack[lis] = govtrack_id

        bioguide = ids.get("bioguide")
        if bioguide:
            bioguide_to_govtrack[bioguide] = govtrack_id

    return lis_to_govtrack, bioguide_to_govtrack


def parse_ideology_file(txt_path):
    """Return dict of govtrack_person_id (int) → ideology_score (float)."""
    scores = {}
    with open(txt_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                person_id = int(row["ID"])
                ideology  = float(row["ideology"])
                scores[person_id] = ideology
            except (ValueError, KeyError):
                continue
    return scores


def normalize_ideology(score, min_score, max_score):
    """Map ideology to 0-1 where 0=most progressive, 1=most conservative."""
    if max_score == min_score:
        return 0.5
    return (score - min_score) / (max_score - min_score)


def main():
    print("Building ID crosswalk from legislators YAML...")
    lis_to_govtrack, bioguide_to_govtrack = build_crosswalk(RAW_YAML)
    print(f"  LIS → GovTrack mappings: {len(lis_to_govtrack)}")
    print(f"  Bioguide → GovTrack mappings: {len(bioguide_to_govtrack)}")

    print("Parsing GovTrack ideology scores...")
    senate_scores = parse_ideology_file(RAW_S_TXT)
    house_scores  = parse_ideology_file(RAW_H_TXT)
    all_ideology  = {**senate_scores, **house_scores}
    print(f"  Senate ideology scores: {len(senate_scores)}")
    print(f"  House ideology scores:  {len(house_scores)}")
    print(f"  Total unique GovTrack IDs: {len(all_ideology)}")

    # Compute normalization range across all legislators
    all_values = list(all_ideology.values())
    min_score  = min(all_values)
    max_score  = max(all_values)
    print(f"  Ideology range: {min_score:.4f} – {max_score:.4f}")

    print("Reading federal key vote scores...")
    with open(KV_SCORES) as f:
        kv_rows = list(csv.DictReader(f))
    print(f"  Key vote rows: {len(kv_rows)}")

    # Save flat ideology mapping for inspection
    ideology_rows = []
    for member_row in kv_rows:
        member_id = member_row["member_id"]
        chamber   = member_row["chamber"]

        if chamber == "senate":
            govtrack_id = lis_to_govtrack.get(member_id)
        else:
            govtrack_id = bioguide_to_govtrack.get(member_id)

        raw_ideology = all_ideology.get(govtrack_id) if govtrack_id else None

        if raw_ideology is not None:
            norm    = normalize_ideology(raw_ideology, min_score, max_score)
            inverse = 1.0 - norm
        else:
            norm    = None
            inverse = None

        ideology_rows.append({
            "member_id":            member_id,
            "name":                 member_row["member_name"],
            "state":                member_row["state"],
            "party":                member_row["party"],
            "chamber":              chamber,
            "district":             member_row.get("district", ""),
            "govtrack_id":          govtrack_id,
            "ideology_score_raw":   raw_ideology,
            "ideology_score_norm":  norm,
            "inverse_ideology_score": inverse,
        })

    with open(OUT_IDEOLOGY, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "member_id", "name", "state", "party", "chamber", "district",
            "govtrack_id", "ideology_score_raw", "ideology_score_norm",
            "inverse_ideology_score",
        ])
        writer.writeheader()
        writer.writerows(ideology_rows)
    print(f"  Wrote {OUT_IDEOLOGY}")

    # Compute combined P2
    combined_rows = []
    coverage_counts = {"both": 0, "key_vote_only": 0, "ideology_only": 0, "neither": 0}

    for kv_row, ideo_row in zip(kv_rows, ideology_rows):
        kv_score   = float(kv_row["key_vote_score"]) if kv_row["key_vote_score"] != "" else None
        votes_cast = int(kv_row["votes_cast"]) if kv_row["votes_cast"] != "" else 0
        inverse    = ideo_row["inverse_ideology_score"]

        has_kv     = votes_cast > 0 and kv_score is not None
        has_ideo   = inverse is not None

        if has_kv and has_ideo:
            p2_combined   = (kv_score * KEY_VOTE_WEIGHT) + (inverse * IDEOLOGY_WEIGHT)
            coverage_type = "both"
        elif has_kv and not has_ideo:
            p2_combined   = kv_score
            coverage_type = "key_vote_only"
        elif not has_kv and has_ideo:
            p2_combined   = inverse * IDEOLOGY_WEIGHT
            coverage_type = "ideology_only"
        else:
            p2_combined   = None
            coverage_type = "neither"

        coverage_counts[coverage_type] += 1

        combined_rows.append({
            "bioguide_id":           kv_row["member_id"],
            "name":                  kv_row["member_name"],
            "state":                 kv_row["state"],
            "party":                 kv_row["party"],
            "chamber":               kv_row["chamber"],
            "district":              kv_row.get("district", ""),
            "key_vote_score":        kv_score if kv_score is not None else "",
            "ideology_score":        ideo_row["ideology_score_raw"],
            "inverse_ideology_score": inverse,
            "p2_combined":           round(p2_combined, 6) if p2_combined is not None else "",
            "coverage_type":         coverage_type,
        })

    with open(OUT_COMBINED, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "bioguide_id", "name", "state", "party", "chamber", "district",
            "key_vote_score", "ideology_score", "inverse_ideology_score",
            "p2_combined", "coverage_type",
        ])
        writer.writeheader()
        writer.writerows(combined_rows)
    print(f"  Wrote {OUT_COMBINED}")

    # Validation report
    print("\n=== VALIDATION ===")
    print(f"Coverage breakdown:")
    for ctype, count in coverage_counts.items():
        print(f"  {ctype}: {count}")

    p2_vals = [float(r["p2_combined"]) for r in combined_rows if r["p2_combined"] != ""]
    if p2_vals:
        sorted_vals = sorted(p2_vals)
        n = len(sorted_vals)
        print(f"\nP2 combined distribution (n={n}):")
        print(f"  min:    {sorted_vals[0]:.4f}")
        print(f"  median: {sorted_vals[n//2]:.4f}")
        print(f"  p75:    {sorted_vals[int(n*0.75)]:.4f}")
        print(f"  p90:    {sorted_vals[int(n*0.90)]:.4f}")
        print(f"  max:    {sorted_vals[-1]:.4f}")

    # Spot checks
    spot_checks = {
        "AOC (Alexandria Ocasio-Cortez)":  "O000172",  # progressive D house
        "Mark Warner (moderate D)":         "S327",
        "Lisa Murkowski (R crossover)":     "S288",
        "Joe Manchin":                      "S338",
        "Mitch McConnell":                  "S174",
        "Bernie Sanders":                   "S313",
    }
    print("\nSpot checks:")
    row_by_id = {r["bioguide_id"]: r for r in combined_rows}
    for label, mid in spot_checks.items():
        row = row_by_id.get(mid)
        if row:
            print(f"  {label}: kv={row['key_vote_score']}, ideo={row['ideology_score']}, "
                  f"inv_ideo={row['inverse_ideology_score']}, p2={row['p2_combined']}, "
                  f"coverage={row['coverage_type']}")
        else:
            print(f"  {label} [{mid}]: NOT FOUND in key vote scores")


if __name__ == "__main__":
    main()
