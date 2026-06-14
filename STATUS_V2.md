# TERRAIN — Migration Status v2.0
*Tracks progress of the v1→v2.0 migration against MASTER_PLAN.md gates.*
*Update at the end of every migration session.*

---

## Current Gate: Gate 7 — Regression validation before rename

Gate 6 display layer migration complete (2026-06-12).
Map UI cleanup complete (2026-06-12).
Next: validate map renders correctly, then rename county_scores_v2_test.json → county_scores.json.

---

## Agent F — GovTrack Ideology Scores — Complete (2026-06-13)
- [x] GovTrack ideology scores downloaded (119th Congress, sponsorshipanalysis_s/h.txt)
- [x] legislators-current.yaml used for LIS→GovTrack and bioguide→GovTrack crosswalk
- [x] federal_ideology_scores.csv produced (533 legislators)
- [x] federal_p2_combined.csv produced (533 legislators)
- [x] Combined P2 = key_vote × 0.60 + inverse_ideology × 0.40
- Coverage: 365 legislators with both signals, 167 key_vote_only, 0 ideology_only, 1 neither
- Ideology range: 0.0 (most progressive) to 1.0 (most conservative), from GovTrack sponsorship analysis
- Spot checks: Bernie=1.0, AOC=0.948, McConnell=0.126, Manchin=0.5 (key_vote_only, retired)
- Note: ideology from 119th Congress, key votes from 117th — 167 members retired/lost seats between congresses

---

## Agent E — State P2 Alignment (COMPLETE, 2026-06-14)

### Approach: DIME CFscores + Open States legislator roster
- Floor vote approach abandoned: state labor bills die in committee in most states
  and do not produce floor votes. This is a structural reality, not a data gap.
- Switched to DIME (Database on Ideology, Money in Politics, and Elections) CFscores
  as the primary pro-labor signal for state legislators.
- CFscore normalization: inverse_cfscore = clip((2 - cfscore) / 4, 0, 1)
  Maps cfscore=-2 → 1.0 (most pro-labor), cfscore=+2 → 0.0 (most anti-labor)
- Source: data/raw/dime_recipients_1979_2024.csv (DIME 2024 release, cycles 2018–2022)

### Imputation note (DOCUMENTED LIMITATION)
- 26.6% of state legislators (1,861 of 7,009) had no DIME match in 2018–2022 cycles.
- These legislators receive party-based imputation:
    Republican unmatched → inverse_cfscore = 0.20
    Democrat unmatched   → inverse_cfscore = 0.75
    Independent/other    → inverse_cfscore = 0.50
- match_type = "party_imputed" in state_key_vote_scores.csv
- Reasons for no DIME match: legislator did not run/file in 2018–2022 (term-limited
  predecessor, special election, appointed), or DIME coverage gap for that cycle.
- Common low-match states: NH (47%, very large House), NE (53%, unicameral nonpartisan),
  SD (53%), NJ (53%).

### Final results (2026-06-14)
- [x] DIME loaded: 42,833 records (2018–2022), 25,987 unique (lname, state, chamber) keys
- [x] Open States legislators fetched: 7,527 across all 50 states
- [x] Nebraska chamber fix: unicameral mapped state:upper → 'legislature'
- [x] Match results: 5,532 matched (73.5%), 1,995 party-imputed (26.5%)
- [x] state_key_vote_scores.csv — 7,527 rows, all 50 states
- [x] state_p2_county_alignment.csv — 3,142 counties, all covered (cfscore_plus_imputed)
- [x] Spot checks passed:
      Centre County PA (42027): 0.460
      Green County WI (55045): 0.454  ← higher than AL ✓
      Jefferson County AL (01073): 0.323  ← lower ✓
      Cook County IL (17031): 0.542
      Maricopa County AZ (04013): 0.444
- [x] State ordering directionally correct:
      CA=0.597, IL=0.542, MN=0.458, WI=0.454, PA=0.460, AZ=0.444, GA=0.426, TX=0.383, AL=0.323

## Map UI Cleanup — Complete (2026-06-12)
- [x] Legacy A/B/C sidebar counts replaced with quadrant counts
- [x] Congressional Districts button removed from map sidebar
- [x] Intervention Types overlay removed (v1 legacy)
- [x] QUADRANT_COLORS updated for colorblind accessibility
- [x] Legend: "Strategic Terrain" heading, shortened labels
- [x] Model version indicator added to status bar

## Next Sessions
- [ ] County/MSA info card redesign
  (gallery Congressional card also needs removal — flag for this session)
- [ ] Literature verification
- [ ] Regression design — dependent variable decision needed
- [ ] county_scores_v2_test.json → county_scores.json rename
  (after browser validation confirms v2.0 map correct)

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
- [x] Intro overlay: v2.0 narrative arc and case studies (2026-06-12)
      - 7-slide arc: stakes → dual track → targeting → two scores → key finding → how to read → CTA
      - deploy_now_both = 0 finding highlighted as key insight in Slide 5
      - Case studies use real scores from county_scores_v2_test.json:
        Centre County PA (42027), Green County WI (55045),
        Muskegon County MI (26121), LA County CA (06037)
      - Slide 7 case panel updated: 8 cards covering all 6 active quadrants
        (Warren GA, Centre PA, Clark NV, Green WI, LA County, Maricopa AZ,
        Philadelphia PA, Montour PA)
      - McAlevey three-forms framework (advocacy/mobilization/organizing) in Slide 2
      - v2.0 scoring dimensions (SLS Capital, SLS Community, P1, P2, Quadrant) in Slide 3
      - Sector SVS updated to real v2.0 values from sector_reach_scores.json
      - No layout, animation, CSS, or scroll-snap changes
- [x] Map UI cleanup — legacy v1 elements removed, accessibility improved (2026-06-12)
      - A/B/C sidebar counts replaced with quadrant distribution counts (Deploy Now / Primary Target / Electoral Leverage / Lower Priority)
      - Congressional Districts [PAUSED] button removed from map sidebar
      - "Show Intervention Types" overlay removed (v1 legacy data — will return in v3.0 with v2.0 classification)
      - QUADRANT_COLORS updated for colorblind accessibility (burnt orange, amber, dark goldenrod, stronger blue)
      - Legend heading: "7-Category Quadrant" → "Strategic Terrain"
      - Legend labels shortened (Capital Target, Community Target, Electoral Leverage)
      - Model version indicator: "Terrain v2.0 · Data: 2024" in status bar
      - Attribution line "Model v2.0 · Data: 2024 · laborterrain.net" in legend
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

House member district field fixed: enriched via Congress.gov Members API bulk + individual fallback + at-large hardcode.
District → county mapping built: scripts/build_p2_county_scores.py via district_county_crosswalk.csv.
p2_county_alignment.csv produced: 3,142 counties, 3,035 house_and_senate, 107 senate_only.
Campaign finance (Capitol Trace): key not in .env — Phase 4C per Sam.

Spot-check validation (2026-06-12):
- Philadelphia PA (42101): score=0.9929  legislators=5  coverage=house_and_senate  ✓
- Centre County PA (42027): score=0.1295  legislators=3  coverage=house_and_senate  ✓
- Green County WI (55045): score=0.9151  legislators=3  coverage=house_and_senate  ✓
- LA County CA (06037):    score=0.9036  legislators=18 coverage=house_and_senate  ✓
- Maricopa County AZ (04013): score=0.4769 legislators=11 coverage=house_and_senate  ✓

Senate weighting: equal across all counties in state (approximation — population weighting deferred Phase 4C).

P2 federal layer status:
- [x] config/key_votes.json — 4 confirmed votes
- [x] scripts/ingest_congress_votes.py — House + Senate ingestion complete
- [x] data/processed/federal_key_votes.csv — 1,063 member-vote records
- [x] data/processed/federal_key_vote_scores.csv — 533 members scored
- [x] House district field populated
- [x] scripts/build_p2_county_scores.py — district→county aggregation
- [x] data/processed/p2_county_alignment.csv — 3,142 counties
- [ ] State legislative votes — Agent E (next)
- [ ] Business funding share — Agent F (next)
- [ ] P2 added to quadrant classification — blocked on E + F

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
