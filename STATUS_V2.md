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

## Phase 4 — Full Scoring Pipeline
- [x] Agent A: `data/processed/sector_reach_scores.json` (42 sectors, cap/comm reach exported)
- [x] Agent A: `data/processed/county_sector_employment.json` (3,143 counties, 101,917 records)
- [ ] Agent B: `district_county_crosswalk.csv` — pending
- [ ] Agent C: `federal_key_votes.csv` — pending
- [ ] Agent D: full scoring run with true SLS formula — pending
  - **Note:** Before producing final scores, Agent D must calculate the actual maximum
    raw SLS-Capital sum across all 3,143 counties using the exported employment data,
    then update `config/weights.json` `svs_normalization.denominator` (currently 100,000)
    to that maximum value. This ensures the 0–100 scale reflects real data range.

### Agent A Notes (2026-06-12)
- 38,272 employment records skipped (no sector relation) — these are QCEW government-sector
  records (NAICS prefix 9) not yet linked to the sector taxonomy in Notion. CBP-sourced records
  are fully linked.
- LA County (06037) raw SLS-Capital: 1,889,256; normalized /1M = 1.89; SLS-Community = 0.83

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
