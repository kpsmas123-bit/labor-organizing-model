# State-Legislative Competitiveness — Ingest Progress & Coverage

**Branch:** `state-leg-margins-ingest` · **Agent 2** · best-effort data task
**Output:** [`data/processed/state_leg_competitiveness.csv`](data/processed/state_leg_competitiveness.csv)
(3,144 rows — one per canonical county, keyed to the live model's FIPS scheme incl. CT planning regions 09110–09190)

---

## ⚠️ NEEDS SAM (read first)

1. **The task's stated inputs did not exist as described — I built around it.**
   - `data/processed/district_county_crosswalk.csv` is a **congressional** crosswalk (441 districts), **not** state-legislative. There was **no** state-leg→county crosswalk in the repo (the project already documents this in `scripts/ingest_openstates.py`: *"no state-leg district crosswalk available"*).
   - I built a real one from the **Census 2022 State-Legislative Block Equivalency Files** → `data/work_stateleg/sld_county_crosswalk.csv` (6,844 districts → counties).
   - The "MIT presidential margins already in repo" = `county_scores.json` field `margin_2024` (D–R %, already in canonical CT FIPS). Used directly as the Tier C floor.

2. **No clean national source of *current* state-leg race margins exists.** The best is **MEDSL "State Legislative Election Returns, 1967–2022"** — it stops at the **2022** general election. **2023/2024 state-leg results are NOT incorporated.** Tier A margins are therefore 2022-vintage (or the most recent prior cycle for 4-yr senate seats). This is the documented "most current obtainable from a clean compilation," not live data.

3. **Three states fully demoted to presidential (Tier C) — recommend manual ingest of their 2023 results:**
   - **VA, NJ, MS** adopted new maps and held **2023** elections (not in MEDSL). MEDSL's pre-2022 district numbers refer to *old* geography that does not align with the 2022 crosswalk, so Tier A there would attach margins to the wrong districts. Demoted to presidential and flagged. These are exactly the states where real state-leg margins would add the most value → **good candidates for a manual / scraped 2023 backfill.**

4. **Tier B (gubernatorial) was NOT implemented.** There is no clean national *county-level* gubernatorial returns file comparable to the presidential one (MIT/tonmcg only publish presidential by county). Counties without Tier A fall straight from A → C. For the demoted/odd-year states above (VA, NJ, MS, LA), a county-level gubernatorial layer would be the most valuable Tier-B addition if Sam wants it.

5. **Louisiana & Nebraska are structural gaps (expected):** NE is a **nonpartisan unicameral** legislature (no D–R margins); LA is **absent from MEDSL entirely** (jungle-primary system doesn't fit the D-vs-R contest model). Both fall to presidential. **Connecticut** falls to presidential because the BEF blocks use *old* CT county FIPS (09001–09015) while the canonical model uses the new planning regions (09110–09190); the join was left to Tier C rather than risk a bad old→new translation. **DC / VT** also presidential (no partisan state leg / named multi-member districts).

---

## Method (the cascade actually built)

Per county, using the **most competitive state-leg seat it touches**:

| Tier | `p1_data_tier` | Source | Notes |
|---|---|---|---|
| A | `district_actual` | MEDSL SLERs 1967–2022 (contest file) | D–R margin of most recent (≥2018) contest per district; uncontested seats resolved to ±100 via win flags |
| B | *(gubernatorial)* | — | **not implemented** (no clean national county source) |
| C | `presidential` | `county_scores.json` `margin_2024` | county presidential D–R %, the documented floor |
| — | `none` | — | 0 counties (presidential covers all) |

**Crosswalk:** Census 2022 SLDU/SLDL Block Equivalency Files → block→district; county = block GEOID[:5]. A district "covers" a county if it holds ≥1% of the county's blocks (`SHARE_MIN`, drops boundary slivers).

**Aggregation rule (DOCUMENTED — scoring agent may re-aggregate):** a county's `margin` = the **minimum |margin| among the non-stale seats covering it** ("most competitive seat the county touches"); `competitive = |margin| ≤ 3`. Current-map (2022) seats are preferred; a pre-2022 senate seat is used only if no 2022 seat covers the county (8 counties, flagged `(pre-2022 map)` in `source`, `vintage=2020`). A richer per-seat file — [`data/work_stateleg/county_seat_detail.json`](data/work_stateleg/county_seat_detail.json) — lists every covering seat (id, margin, year, block share, stale) so an overlap-weighted alternative can be computed without re-running the join.

**Stale detection:** current Open States roster (`data/processed/state_key_vote_scores.csv`, generated 2026-06) party vs MEDSL 2022 winner party. A district is stale when both are D/R and differ (captures specials & party switches; ignores independents). 305 districts flagged. A **county** is flagged `margin_stale = true` (147 counties) when a *dropped stale seat was more competitive than the chosen seat* — i.e. the county's competitiveness may be understated. (Per spec, stale seats are dropped rather than kept; no special-election replacement margins were available to substitute.)

## Output columns
`fips, state, district_ids, margin, competitive, p1_data_tier, margin_stale, source, vintage`
(`district_ids` = `;`-joined seats used for the county; `state` added for convenience.)

## Headline coverage
- **3,144 / 3,144** counties have a value (0 `none`).
- **Tier A `district_actual`: 2,712 (86.3%)** — 2,704 on current 2022 maps, 8 on a flagged pre-2022 senate seat.
- **Tier C `presidential`: 432 (13.7%)**.
- **194 counties competitive** (touch a seat within 3%); **147** flagged `margin_stale`.
- MEDSL districts matched to crosswalk: 5,934 / 6,091 with a margin; 305 stale.

## Per-state coverage
`actual` = Tier A counties · `pres` = Tier C counties · `comp` = competitive counties · `stale` = stale-flagged counties.

| ST | counties | actual | pres | comp | stale |
|----|---:|---:|---:|---:|---:|
| AK | 30 | 30 | 0 | 11 | 2 |
| AL | 67 | 67 | 0 | 0 | 1 |
| AR | 75 | 75 | 0 | 7 | 1 |
| AZ | 15 | 15 | 0 | 2 | 1 |
| CA | 58 | 58 | 0 | 10 | 5 |
| CO | 64 | 64 | 0 | 6 | 2 |
| CT | 9 | 0 | 9 | 1 | 0 |
| DC | 1 | 0 | 1 | 0 | 0 |
| DE | 3 | 3 | 0 | 1 | 1 |
| FL | 67 | 67 | 0 | 2 | 3 |
| GA | 159 | 159 | 0 | 0 | 10 |
| HI | 5 | 5 | 0 | 1 | 2 |
| IA | 99 | 99 | 0 | 4 | 5 |
| ID | 44 | 44 | 0 | 6 | 1 |
| IL | 102 | 102 | 0 | 10 | 0 |
| IN | 92 | 92 | 0 | 8 | 0 |
| KS | 105 | 105 | 0 | 2 | 6 |
| KY | 120 | 120 | 0 | 2 | 2 |
| LA | 64 | 0 | 64 | 3 | 0 |
| MA | 14 | 8 | 6 | 0 | 0 |
| MD | 24 | 24 | 0 | 1 | 0 |
| ME | 16 | 16 | 0 | 4 | 8 |
| MI | 83 | 83 | 0 | 10 | 5 |
| MN | 87 | 87 | 0 | 8 | 0 |
| MO | 115 | 115 | 0 | 5 | 2 |
| MS | 82 | 0 | 82 | 3 | 0 |
| MT | 56 | 54 | 2 | 8 | 12 |
| NC | 100 | 100 | 0 | 3 | 5 |
| ND | 53 | 52 | 1 | 2 | 3 |
| NE | 93 | 0 | 93 | 0 | 0 |
| NH | 10 | 10 | 0 | 3 | 0 |
| NJ | 21 | 0 | 21 | 3 | 0 |
| NM | 33 | 33 | 0 | 6 | 6 |
| NV | 17 | 17 | 0 | 1 | 1 |
| NY | 62 | 62 | 0 | 11 | 3 |
| OH | 88 | 88 | 0 | 5 | 5 |
| OK | 77 | 77 | 0 | 0 | 0 |
| OR | 36 | 36 | 0 | 3 | 4 |
| PA | 67 | 67 | 0 | 4 | 1 |
| RI | 5 | 5 | 0 | 2 | 1 |
| SC | 46 | 46 | 0 | 1 | 10 |
| SD | 66 | 60 | 6 | 4 | 11 |
| TN | 95 | 95 | 0 | 1 | 0 |
| TX | 254 | 254 | 0 | 1 | 8 |
| UT | 29 | 29 | 0 | 1 | 2 |
| VA | 133 | 0 | 133 | 5 | 0 |
| VT | 14 | 0 | 14 | 2 | 0 |
| WA | 39 | 39 | 0 | 6 | 0 |
| WI | 72 | 72 | 0 | 12 | 14 |
| WV | 55 | 55 | 0 | 3 | 3 |
| WY | 23 | 23 | 0 | 0 | 1 |

### States to review
- **Zero Tier A (fall fully to presidential):** CT (FIPS), DC (no partisan leg), LA (MEDSL excl.), NE (nonpartisan unicameral), VT (named multi-member districts), **VA / NJ / MS (demoted — map change, see NEEDS SAM #3).**
- **Partial Tier A** (named/multi-member or unmatched districts → some counties on presidential): MA (8/14), MT (54/56), ND (52/53), SD (60/66).

## Reproduce
`python3 scripts/ingest_state_leg_competitiveness.py`
Raw sources are re-downloaded into `data/work_stateleg/` (BEF zips + MEDSL `.tab`, gitignored due to size): see script header for URLs/DOIs. Committed work artifacts: the SLD→county crosswalk and the per-seat detail JSON.

## Provenance
- MEDSL State Legislative Election Returns 1967–2022 — doi:10.7910/DVN/FJOGJB
- Census 2022 SLD Block Equivalency Files — census.gov RDO 2023
- Open States current roster — via existing `data/processed/state_key_vote_scores.csv`
- Presidential floor — `county_scores.json` `margin_2024` (MIT/tonmcg)
