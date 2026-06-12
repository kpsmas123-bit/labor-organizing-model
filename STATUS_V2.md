# TERRAIN — Migration Status v2.0
*Tracks progress of the v1→v2.0 migration against MASTER_PLAN.md gates.*
*Update at the end of every migration session.*

---

## Current Gate: 3 — Extract scoring functions to scoring/

Config layer is in place. Regression tests are passing. Safe to begin extracting scoring
functions to `scoring/` in the next session.

---

## Phase 1 — Config Layer
- [x] `config/weights.json` created and verified
- [x] `config/thresholds.json` created and verified
- [x] `task9_fast.py` reads from config (smoke test passed)
- [x] Four deprecated scripts frozen
- [x] 79 regression tests passing
- [ ] `config/key_votes.json` — Gate 3
- [ ] `config/normalization.json` — Gate 3

---

## Gate 1 Complete (Main Repo) — 2026-06-11

### Freeze Comments
- [x] `scripts/task9_score_counties.py` — freeze comment added
- [x] `scripts/export_county_scores.py` — freeze comment added
- [x] `scripts/score_strike_activity.py` — freeze comment added
- [x] `scripts/task3_sectors.py` — freeze comment added

### Config Layer
- [x] `config/` directory created
- [x] `config/weights.json` — all formula weights from task9_fast.py + score_strike_activity.py
- [x] `config/thresholds.json` — all classification thresholds from task9_fast.py + score_strike_activity.py
- [x] `task9_fast.py` wired: `score_organizing_opportunity()`, `score_organizing_potential()` Part C,
  `classify_intervention()`, `priority_tier()` all read from config
- [x] Smoke test: `from scripts.task9_fast import _WEIGHTS, _THRESHOLDS` — Config loaded OK

### Regression Tests
- [x] `tests/test_scoring_regression.py` copied from Gate 2 worktree
- [x] 79/79 tests passing in main repo against config-wired functions

### Next Session
Gate 3: Extract scoring functions to `scoring/` modules.
Pre-condition: ✅ config layer complete, ✅ regression tests in place.

---

## Agent B — Census Crosswalk (2026-06-11)
- [x] Agent B: `data/processed/district_county_crosswalk.csv` — 3,838 district-county pairs, 441 districts, all weight sums within 5% of 1.0
- [x] Agent B: `data/processed/chamber_seat_counts.json` — 97 chambers across 50 states, tipping weights calculated
- [x] Agent B: `scripts/ingest_census_crosswalk.py` — ingestion + validation script

**Crosswalk notes:**
- Source: Census tab20_cd11820_county20_natl.txt (118th Congress, 2020 geographies), found at `rel2020/cd-sld/` not `rel2020/cd118/`
- overlap_weight = AREALAND_PART / AREALAND_CD118_20 (fraction of district in each county)
- 9 CT FIPS (09110–09190) are Connecticut Planning Regions (new 2022 geography), not in 2020 Census crosswalk — those counties will have null P1 Congressional/State Leg scores until CT crosswalk is resolved
- 7 rows skipped: at-large/non-voting districts with zero land area
- Unblocks Phase 3: `scoring/p1_congressional.py` and `scoring/p1_state_leg.py`

---

## Gate Status

| Gate | Description | Status |
|---|---|---|
| 1 | Config layer foundation + freeze scripts | ✅ Complete (2026-06-11) |
| 2 | Regression tests + archival analysis | ✅ Complete (worktree, 2026-06-11) |
| 3 | Extract scoring functions to `scoring/` | ⬜ Ready to begin |
| 4 | Rewrite ingestion scripts to `ingestion/` | ⬜ Blocked on Gate 3 |
| 5 | Build `pipeline/build_county_scores.py` | ⬜ Blocked on Gate 4 |
| 6 | Full 3,144-county validation run | ⬜ Requires Sam approval |
| 7 | Display layer migration | ⬜ Blocked on Gate 6 |
