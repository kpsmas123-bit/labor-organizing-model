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
- [x] `config/key_votes.json` — 4 confirmed votes, all verified against senate.gov XML and clerk.house.gov
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

### Agent C Session (2026-06-11) — COMPLETE
Data source change: ProPublica Congress API deprecated; replaced with:
- House Clerk XML `clerk.house.gov/evs/{year}/roll{NNN}.xml` (117th Congress votes)
- Senate.gov XML `senate.gov/legislative/LIS/roll_call_votes/...` (Senate votes)
- Congress.gov API v3 `/v3/house-vote/...` (118th Congress+ when needed)

Files created/updated:
- `config/key_votes.json` — 4 confirmed votes, all roll call numbers verified against official XML
- `scripts/ingest_congress_votes.py` — replaces ingest_propublica.py (handles House Clerk XML + Senate XML + Congress.gov API)
- `data/processed/federal_key_votes.csv` — 1,063 member-vote records across 4 votes
- `data/processed/federal_key_vote_scores.csv` — 533 unique members scored

Key vote score results:
- House: 220 Democrats 1.0, 183 Republicans 0.0, 5 Republicans 1.0 (crossover), 23 Republicans partial
- Senate: 42 Democrats/Independents 1.0, 50 Republicans 0.0, 7 Democrats partial (0.5)
- 7 partial Senate Dems all voted YES on Abruzzo + NO on Sanders MW: Manchin, Sinema, Coons, Carper, Tester, Shaheen, Hassan
- Median score: 1.0 (driven by Democratic majority on House votes)

Known limitation: House member district field is empty (House Clerk XML district parsing to investigate).
Campaign finance (Capitol Trace): key not in .env — Phase 4C per Sam.

### Next Session
Gate 3: Extract scoring functions to `scoring/` modules.
Pre-condition: ✅ config layer complete, ✅ regression tests in place.

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
