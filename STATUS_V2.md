# TERRAIN — Migration Status v2.0
*Tracks progress of the v1→v2.0 migration against MASTER_PLAN.md gates.*
*Update at the end of every migration session.*

---

## Current Gate: 6 — Display layer migration

Gate 5 complete. v2.0 scoring pipeline built and validated. All 3,144 counties scored.
Next: update display layer to read v2.0 fields from county_scores_v2_test.json.

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

## Phase 4 — First v2.0 Scoring Run (Gate 5)
- [x] `data/state_tipping_weights.json` created (2024 cycle, 538-derived)
- [x] `pipeline/build_v2_scores.py` written — v2.0 scoring orchestrator
- [x] `scoring/sls.py` created — SLS-Capital and SLS-Community functions
- [x] `scoring/electoral.py` created — P1 Presidential continuous formula
- [x] 50-county test run complete — Sam reviewed
- [x] Full 3,144-county run complete — 0 errors
- [x] `data/county_scores_v2_test.json` produced
- [x] P1 threshold calibrated to 5 after reviewing full distribution
- [ ] Display layer update — Gate 6

### Scoring notes
- SLS scores are proxies (v1 `sectoral_score` as stand-in). True formula requires per-sector Notion data (Phase 4 full pipeline).
- P1 Presidential uses v2.0 continuous formula: `tipping_weight × (1/margin) × 357.14`
- P1 threshold set to 5 = top 3.1% nationally (96 counties), all genuine swing counties in decisive states.

---

## Gate Status

| Gate | Description | Status |
|---|---|---|
| 1 | Config layer foundation + freeze scripts | ✅ Complete (2026-06-11) |
| 2 | Regression tests + archival analysis | ✅ Complete (worktree, 2026-06-11) |
| 3 | Extract scoring functions to `scoring/` | ✅ Complete (2026-06-11, Gate 5) |
| 4 | Rewrite ingestion scripts to `ingestion/` | ⬜ Blocked on Gate 3 |
| 5 | First v2.0 scoring run | ✅ Complete (2026-06-11) |
| 6 | Display layer migration | ⬜ Ready to begin |
| 7 | Full pipeline (per-sector Notion data) | ⬜ Blocked on Gate 4 |
