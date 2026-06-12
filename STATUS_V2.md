# TERRAIN — Migration Status v2.0
*Tracks progress of the v1→v2.0 migration against MASTER_PLAN.md gates.*
*Update at the end of every migration session.*

---

## Current Gate: Gate 7 — Regression validation before rename

Gate 6 display layer migration complete (2026-06-12).
Next: validate map renders correctly, then rename county_scores_v2_test.json → county_scores.json.

---

## Phase 5 — Display Layer
- [x] Data source switched to county_scores_v2_test.json
- [x] Lens system reads sls_capital and sls_community directly
- [x] JENKS thresholds recalibrated for v2.0 score distribution [0.5,1.5,3,8,20]
- [x] Goal toggle: Power Building uses 7-category quadrant colors
- [x] Goal toggle: Presidential Swing uses p1_presidential score
- [x] NC swing state display bug fixed (added NC to SWING_STATES_PRES)
- [x] Detail panel updated to v2.0 field names and labels
- [x] Quadrant badge with human-readable QUADRANT_LABELS
- [x] Deprecated v1 fields commented out (terrain_score, priority_tier, OOS)
- [x] _setBar null-safe for removed bar elements
- [x] MSA layer (Gate 6b): classifyMsaQuadrant() using threshold comparison on aggregated scores
- [x] MSA layer: sls_capital/sls_community/p1_presidential named fields on msaScore object
- [x] MSA layer: FIPS join confirmed working via msa_lookup.json enrichment at load time
- [x] Detail panel label: "Capital Leverage" → "Strategic Leverage"
- [x] p2_alignment null safety: shows "Data pending" instead of "–"
- [ ] Intro overlay update — separate future session
- [ ] county_scores_v2_test.json → county_scores.json rename — after regression validation

---

## Phase 4 — Full Scoring Pipeline
- [x] Agent A: sector reach scores + county employment exported
- [x] Agent B: district-county crosswalk + chamber seat counts
- [x] Agent C: federal key votes (4 votes, 533 members scored)
- [x] Agent D: true v2.0 scoring run complete
- [x] config/weights.json denominator recalibrated to 210,000
- [x] county_scores_v2_test.json: real scores, 7-quadrant system
- [x] All agent branches merged to main
- [x] Gate 6: display layer update — COMPLETE

### Agent D Notes (2026-06-12)
- SLS-Capital: min=0.00, median=0.23, p75=0.72, p90=2.38, p95=5.21, max=84.16
- SLS-Community: min=0.00, median=21.24, p75=27.68, p90=34.64, p95=39.89, max=82.67
- P1 Presidential: min=0.02, median=0.06, p75=0.28, p90=1.60, p95=2.87, max=100.00
- P1 Congressional: min=0.00, median=0.00, p75=0.13, p90=1.48, p95=2.78, max=100.00
- P2 Alignment: min=0.00, median=0.33, p75=0.59, p90=0.80, p95=0.83, max=1.00
- Quadrant (placeholder threshold=50): Q2=4, Q3=95, Q4=3,044
- Known limitations: P1 Congressional uses county margin as district proxy;
  P2 uses state-level averaging (district field empty in Agent C source)
- deploy_now_both = 0: No county currently clears both SLS-Capital >= 2.5,
  SLS-Community >= 35, AND P1 >= 5. This reflects the structural reality
  that major labor metros are concentrated in non-swing states.
  This is a genuine finding, not a calibration error.
- Small county amplification: SLS-Community uses workforce share,
  which can produce high scores in tiny rural counties where a single
  sector dominates local employment. Niobrara WY (pop. 2,354) scores
  43.1 on community reach. This is methodologically correct but
  strategically limited by absolute workforce scale.
  Future versions may add a minimum workforce floor.

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
