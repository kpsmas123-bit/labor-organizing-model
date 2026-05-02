# Execution Order

## Prerequisites
1. Fill in `config.json` — Notion API key + 6 database IDs + BLS API key
2. Create the 6 Notion databases using the schemas in the build spec
3. `pip install requests`

## Week 1: Foundation

```bash
cd scripts

# Seed sectors first (needed for relations)
python task3_sectors.py --config ../config.json
python export_page_ids.py --config ../config.json --db sectors

# Upload all 3,143 counties
python task1_counties.py --config ../config.json
python export_page_ids.py --config ../config.json --db counties

# Upload 51 states
python task2_states.py --config ../config.json
python export_page_ids.py --config ../config.json --db states
```

## Week 2: Employment Data

```bash
# Phase 1: top 100 counties (most impactful, ~2,000 BLS queries)
python task4_bls_employment.py --config ../config.json --phase 1

# Phase 2: next 400 counties
python task4_bls_employment.py --config ../config.json --phase 2

# Phase 3: remaining ~2,600 counties (many will have suppressed data)
python task4_bls_employment.py --config ../config.json --phase 3
```

## Week 3: Political Data

```bash
python task5_elections.py --config ../config.json
```

## Week 4: Union Density

```bash
# Update states with RTW/density, then estimate union members in employment records
python task6_union_density.py --config ../config.json --pass 0
```

## Week 5: Union Directory + Strikes

```bash
python task7_lm2_unions.py --config ../config.json --year 2023
python export_page_ids.py --config ../config.json --db unions

python task8_strikes.py --config ../config.json
```

## Week 6: Scoring + Dashboard

```bash
# Score all counties (reads from all tables, writes scores back)
python task9_score_counties.py --config ../config.json

# Export scores to JSON for dashboard
python export_county_scores.py --config ../config.json
# → writes data/county_scores.json

# Open the dashboard
open ../output/labor_organizing_national_dashboard.html
```

## Testing a single county before full run

```bash
# Dry-run county upload (shows first 3 records, no writes)
python task1_counties.py --config ../config.json --dry-run

# Score just LA County to validate logic
python task9_score_counties.py --config ../config.json --fips 06037
```

## Validation checks
- Cook County IL (17031) and Clark County NV (32003) should be Tier A
- Rural Wyoming counties should be Tier C
- Swing state counties should have Electoral Geography Score ≥ 60
- Distribution target: ~10-15% Tier A, ~30-40% Tier B, ~50% Tier C
