# TERRAIN — Migration Status v2.0
*Tracks progress of the v1→v2.0 migration against MASTER_PLAN.md gates.*
*Update at the end of every migration session.*

---

## Current Gate: 4 — Remove local fallback definitions from task9_fast.py

scoring/ layer is in place. All 133 tests passing (79 regression + 54 v2).
Safe to begin removing local fallback definitions from task9_fast.py in the next session.

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

## Phase 3 — Scoring Layer
- [x] scoring/__init__.py created
- [x] scoring/svs.py — SVS formula as pure function
- [x] scoring/sls.py — SLS-Capital and SLS-Community
- [x] scoring/electoral.py — legacy + new P1 functions
- [x] scoring/infrastructure.py — organized scale, culture, infra, intervention
- [x] task9_fast.py imports from scoring/ (local definitions kept as fallback)
- [x] tests/test_scoring_v2.py — 54 tests, all passing
- [x] 11 files archived to docs/archive/
- [ ] Remove local fallback definitions from task9_fast.py — Gate 4
- [ ] scoring/p2_alignment.py — Phase 2C data required

---

## Gate Status

| Gate | Description | Status |
|---|---|---|
| 1 | Config layer foundation + freeze scripts | ✅ Complete (2026-06-11) |
| 2 | Regression tests + archival analysis | ✅ Complete (worktree, 2026-06-11) |
| 3 | Extract scoring functions to `scoring/` | ✅ Complete (2026-06-11) |
| 4 | Rewrite ingestion scripts to `ingestion/` | ⬜ Blocked on Gate 3 |
| 5 | Build `pipeline/build_county_scores.py` | ⬜ Blocked on Gate 4 |
| 6 | Full 3,144-county validation run | ⬜ Requires Sam approval |
| 7 | Display layer migration | ⬜ Blocked on Gate 6 |
