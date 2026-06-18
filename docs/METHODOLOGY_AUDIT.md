# Methodology Audit — Ground-Truth Spec (read-only)

Extracted from code/config/data on `main` (commit `e06b940`). Every claim is cited to
`file:line`. Comments and section titles were NOT trusted; the actual computation was traced.
This document changes nothing in the model — it is the factual reference the prose is written from.

**The live pipeline that produces `data/county_scores.json`:**
1. `pipeline/build_v2_canonical.py --full` → writes all fields (SLS, national P1/P2, state P1/P2 via the *inverse-margin* formula, both quadrants).
2. `pipeline/rebuild_state_lens.py --write` → **overwrites** the state-lens fields (`p1_state`, `p2_state`, `quadrant_state`, `state_p2_coverage`, `p1_state_data_tier`, `margin_stale`, `state_noncomp_priority`) with the *plateau-fade* formula. National + SLS fields are asserted untouched.
3. `output/terrain-map.js` + `output/index.html` read the JSON and render map + scatter.

`scoring/sls.py`, `scoring/electoral.py`, `scoring/svs.py`, `scoring/infrastructure.py` are **not imported by the live build** — `scoring/sls.py` is explicitly marked dead code (`scoring/sls.py:1-13`). Trust `build_v2_canonical.py`.

---

# INPUTS

## County employment
1. **Where:** consumed in `calc_sls_capital` (`pipeline/build_v2_canonical.py:84-87`) and `calc_sls_community` (`:105-113`); loaded `build_v2_canonical.py:323` (`data/processed/county_sector_employment.json`, key `employment`).
2. **Inputs / source:** per-county → per-sector dict `{sector_id: {total_employment, data_source}}`. Each record stamped `"data_source": "Census CBP 2023"` (County Business Patterns; public-sector supplemented by BLS QCEW per the index data-source table, `output/index.html:1586-1587`). 3,143 counties.
3. **Cleaning:** none at score time. `calc_sls_community` guards `total == 0 → 0.0` (`:107-108`). Missing sector ids silently skipped (`if sid in sector_points`, `:86`, `:110`).
4. **Calculation:** raw employment counts; sectors filtered to those present in the reach rubric.
5. **Weights/thresholds:** none here.
6. **Output:** not emitted as a field; feeds SLS. (Re-read client-side for the "top strategic sectors" tooltip via `window._countyEmployment`, `output/terrain-map.js:108`.)
7. **Discrepancy flags:** CBP vintage hardcoded "2023" in the data record but the index table lists vintage as "Annual" (`output/index.html:1586`). None material to scoring.

## Sector strategic score (the reach rubric)
1. **Where:** rubric file `data/processed/sector_reach_scores.json` (`sectors` map, 42 sectors). SVS formula in `scoring/svs.py:30-83` (`score_svs`); ordinals→points mapping for SLS in `build_sector_points` (`build_v2_canonical.py:72-81`).
2. **Inputs / source:** per sector — `cap_reach` (0–3), `comm_reach` (0–3), `comm_facing` (0–3), `non_off` (0–2), plus precomputed `svs`, `naics`, `sector_name`. `_source` = Notion database (`sector_reach_scores.json` top keys `_source`, `_database_id`).
3. **Cleaning:** ordinal→label via `ordinal = {0:none,1:local,2:state,3:national}` (`build_v2_canonical.py:73`); unknown ordinals default to `"none"` (`:78-79`).
4. **Calculation (SVS, `scoring/svs.py:70-83`):** `SVS = reach_pts[cap] + reach_pts[comm] + facing_pts[facing] + non_off_pts[non_off] + (dual_crisis_bonus if cap>0 and comm>0) + (whole_worker_bonus if comm_reach>0 and comm_facing>0)`. **For SLS, only `cap_reach`/`comm_reach` are used**, each mapped through `reach_points` (`build_v2_canonical.py:74-80`).
5. **Weights/thresholds (`config/weights.json` `svs_formula`, lines 84-92):** `reach_points {none:0, local:10, state:15, national:25}`; `facing_points {0,5,10,15}`; `non_off_points {none:0, partial:3, full:5}`; `dual_crisis_bonus:5`; `whole_worker_bonus:5`. SVS range 0–80.
6. **Output:** sector-level `svs` is NOT in `county_scores.json`; it surfaces only in the client tooltip "top strategic sectors" (`terrain-map.js:113`, `svs × employment`).
7. **Discrepancy flags:**
   - **The full SVS score (with `comm_facing`, `non_off`, both bonuses) does not feed SLS at all.** SLS uses only the two reach ordinals re-mapped to 10/15/25. The `svs` field is display-only.
   - `scoring/svs.py` reach_points are 0/10/15/25 (config), but the docstring of `scoring/sls.py:54` claims "cap_reach (0-25)" / "comm_reach (0-15)" — a different scale; `sls.py` is dead code (see header).

## Vote margin
1. **Where:** read as `margin = ex.get("margin_2024")` from the prior canonical snapshot (`build_v2_canonical.py:367`, source file `data/county_scores_v2_test.json` loaded `:339-340`). Feeds `score_p1` (national) `:374`. Original capture: `scripts/task9_fast.py:407` (`get_prop(county,"Presidential 2024 Margin","number")`).
2. **Inputs / source:** county 2024 presidential two-party margin in percentage points, **positive = Dem win, negative = Rep win** (`scoring/electoral.py:13`). Origin: MIT Election Data and Science Lab, vintage **2024** (`output/index.html:1588`); routed through Notion → `task9_fast.py` → carried forward via the `existing` dict (never recomputed in the canonical build).
3. **Cleaning:** `None` margin → P1 national = `15.0` (`build_v2_canonical.py:119-120`).
4. **Calculation:** see Electoral Leverage.
5. **Thresholds:** `_MIN_MARGIN_PP = 0.5` floor (`:40`).
6. **Output:** emitted verbatim as `margin_2024` (`:397`). Example `01001` = `-46.28`.
7. **Discrepancy flags:** margin is **read from a previous build's output**, not from a primary returns file in this build — a bootstrap chain (`county_scores_v2_test.json` → canonical). The true upstream (`task5_elections.py`, MIT EDSL) is not invoked here.

## Key votes
1. **Where:** definitions `config/key_votes.json`; scored per-legislator into `data/processed/federal_key_vote_scores.csv` → column `key_vote_score` of `data/processed/federal_p2_combined.csv`. Consumed only as the precomputed `p2_combined` (`build_v2_canonical.py:155-157`).
2. **Inputs / source:** `config/key_votes.json` `federal_votes[]` — 4 votes (e.g. `pro_act_117` PRO Act House RC#70 2021-03-09; `sanders_min_wage_117`; …). Sources: House Clerk XML, Congress.gov API, Senate.gov XML (`config/key_votes.json` `_data_sources`). Index table cites ProPublica/Congress.gov, vintage "Per vote" (`output/index.html:1590,1593`).
3. **Cleaning:** legislators with empty `p2_combined` skipped (`build_v2_canonical.py:155-157`); source already excludes deceased/former members (`:150`).
4. **Calculation:** `key_vote_score` ∈ [0,1] = pro-labor vote share over the defined votes; combined with ideology at the P2 step.
5. **Weights:** `key_vote_score` weighted **0.60** inside `p2_combined` (see Federal P2).
6. **Output:** indirect, via `p2_national`.
7. **Discrepancy flags:** **Only 45/88 senators and 152/277 House members have a non-zero `key_vote_score`** (others 0.0). For those legislators P2 is driven **entirely by ideology** — the "key votes" input is silently absent for ~half the roster. `federal_p2_combined.csv` has 365 rows, all `coverage_type = both`.

## Ideology score
1. **Where:** `data/processed/federal_ideology_scores.csv` → `ideology_score`/`inverse_ideology_score` columns of `federal_p2_combined.csv`; used in `p2_combined`.
2. **Inputs / source:** GovTrack ideology from sponsorship patterns (119th Congress) and DIME CFscores (`output/index.html:1597,1599-1600`). `inverse_ideology_score = 1 − ideology` so higher = more pro-labor.
3. **Cleaning:** precomputed upstream.
4. **Calculation:** weighted **0.40** inside `p2_combined`.
5. **Weights:** 0.40 (see Federal P2).
6. **Output:** indirect, via `p2_national`.
7. **Discrepancy flags:** see Federal P2 — the **0.40 weight is on inverse-ideology, NOT on "inverse business funding"** that `config/weights.json p2_alignment` (lines 94-99) describes.

## Party ID
1. **Where:** state-lens P2 only — `score_p2_state` (`rebuild_state_lens.py:188-205`), source `data/work_stateleg/county_seat_detail.json` (`:68`).
2. **Inputs / source:** per-county list of state-leg seats with `{current_party (D/R/I), share}`. Open States API rosters (`output/index.html:1598`).
3. **Cleaning:** `None`-party seats excluded from denominator; Independents counted in denominator but not Dem numerator (`:201-202`).
4. **Calculation:** `p2_state = Σ share[D] / Σ share[D,R,I]` (`:196-200`). Fallbacks: state-uniform Dem share (`:203-205`), then `0.5` (`:205`).
5. **Thresholds:** consumed by hostile/aligned gates (0.4 / 0.6).
6. **Output:** `p2_state` (0–1), `state_p2_coverage` ∈ {party_proxy (2948), party_proxy_state_uniform (194), party_proxy_unavailable (1)}.
7. **Discrepancy flags:** **state P2 is pure party-ID Dem share** — it uses neither key votes nor campaign finance, contradicting the federal-style "alignment" framing.

---

# FACTORS

## Sectoral Leverage — SLS-Capital + SLS-Community
1. **Where:** `calc_sls_capital` (`build_v2_canonical.py:84-87`), `calc_sls_community` (`:105-113`), `confidence_ramp` (`:90-102`).
2. **Inputs:** county→sector `total_employment`; sector `cap`/`comm` points (10/15/25).
3. **Cleaning/adjustments:** Community gets the **confidence ramp** (Option D noise gate); Capital does not. `total==0 → 0`.
4. **Calculation:**
   - **SLS-Capital (MAGNITUDE):** `raw = Σ_sector cap_points × total_employment`; `score = round(min(100, raw / denominator), 2)` (`:85-87`).
   - **SLS-Community (SHARE):** `weighted = Σ_sector comm_points × (employment / total)`; `share_score = min(100, weighted × 4)`; `score = round(min(100, share_score × ramp), 2)` (`:109-113`).
   - **Confidence ramp:** `1.0` if `total_emp ≥ ramp_full_at`; `0.0` if `≤ ramp_zero_at`; linear between (`:98-102`).
5. **Weights/thresholds:** `denominator = 210000` (`config/weights.json:40`, `svs_normalization`); community `× 4` is **hardcoded** (`:111`); ramp `ramp_full_at=10000`, `ramp_zero_at=2000` (`config/thresholds.json:22-23`).
6. **Output:** `sls_capital` (range 0–84.16, median 0.23), `sls_community` (range 0–56.03, median 8.09).
7. **Discrepancy flags:**
   - **Capital and Community are on fundamentally different semantics** despite the shared "leverage" name: Capital = absolute employment × reach / 210k (rewards size); Community = employment-*share* × reach × 4 × ramp (rewards concentration, suppresses small counties). Their "high" thresholds differ accordingly (2.5 vs 25).
   - The Community `× 4` multiplier is hardcoded, not in config (single-source violation).
   - `denominator` is described as calibrating LA county to ~84 (`weights.json:41-42`); observed max is exactly 84.16 ✓.

## Electoral Leverage (P1)

### National variant (presidential)
1. **Where:** `score_p1` (`build_v2_canonical.py:118-126`), called `:374` with presidential tipping.
2. **Inputs:** `margin_2024`; `state_tipping_weight` (presidential).
3. **Cleaning:** `margin None → 15.0`; `tipping None → None`; `abs_margin = max(0.5, |margin|)`.
4. **Calculation:** `raw = tipping × (1/abs_margin)`; `P1 = round(min(100, raw × NORM), 2)` (`:124-126`).
5. **Weights/thresholds:** `_NORM = 100/0.28 = 357.14` (`:41`); `_MIN_MARGIN_PP=0.5` (`:40`); tipping from `data/state_tipping_weights.json` (PA 0.28 max, swing-7 0.05–0.28, `_default 0.005`, vintage 2024); `_PRES_DEFAULT_TIP=0.005` (`:42`).
6. **Output:** `p1_national` (alias `p1_presidential`). Example `01001` = 0.04.
7. **Discrepancy flags:** `_NORM` is **hardcoded** in code (`:41`), derived from the PA tipping value — if PA's tipping changes, NORM is stale. The "BUG #1 fix" comment (`:42`, `:398`) notes the stored `state_tipping_weight` now equals the value used (previously inconsistent).

### State variant (chamber) — **as actually shipped**
1. **Where:** computed twice. (a) `build_v2_canonical.py:376` via the SAME `score_p1` with chamber tipping; **(b) OVERWRITTEN** by `score_p1_state` (`rebuild_state_lens.py:163-171`) — this is the live value.
2. **Inputs:** state-leg `margin` (two-party pp) from `data/processed/state_leg_competitiveness.csv` (+ `_backfill.csv` overlay); `chamber_flip_proximity` from `chamber_seat_counts.json` `tipping_weights`.
3. **Cleaning:** overlay rows REPLACE base rows by fips (`rebuild_state_lens.py:90-94`); `prox None or margin None → 0.0` floor (DC/DE, `:169-170`). No swing buffer / no synthetic adjustment; stale rows flagged by vintage, not discounted (`thresholds.json:56`).
4. **Calculation:** `P1_state = round(100 × prox × comp(margin), 2)` (`:171`). `comp` = **plateau-fade**: `1.0` for `|m| ≤ plateau_edge`; linear decay to 0 at `zero_edge`; `0.0` beyond (`:135-150`). `prox` = best-seat chamber tipping, fallback state-mean (`:153-160`).
5. **Weights/thresholds (`config/thresholds.json` `state_competitiveness`, lines 47-57):** `plateau_edge=3.0`, `zero_edge=8.0`, `p1_high_state=60.0`. All config-read (`rebuild_state_lens.py:225-227`).
6. **Output:** `p1_state` (0–~98). Also `p1_state_data_tier` (e.g. `district_actual:2022` ×2703, `gubernatorial:2021` ×133, `presidential:2024` ×39), `margin_stale`.
7. **Discrepancy flags:**
   - **Two contradictory P1_state formulas exist.** `build_v2_canonical.py:376` writes an inverse-margin P1_state (same shape as national); `rebuild_state_lens.py` then overwrites it with the unrelated plateau-fade formula. The canonical's value is dead. Anyone reading only `build_v2_canonical.py` would mis-describe the shipped state P1.
   - State P1 is on a **different scale** than national P1 (`thresholds.json:55`) — its "high" gate is 60, vs national 5.

## Incumbent Alignment (P2)

### Federal variant (key votes + ideology)
1. **Where:** `build_federal_p2_indexes` (`build_v2_canonical.py:144-166`), `calc_federal_p2` (`:181-217`), called `:379`.
2. **Inputs:** `p2_combined` per legislator (`federal_p2_combined.csv`); district→county overlap (`district_county_crosswalk.csv`, cols `district_state, district_number, county_fips, overlap_weight`).
3. **Cleaning:** empty `p2_combined` skipped; crosswalk-miss counties (e.g. CT planning-region FIPS) fall back to statewide House delegation (`:199-201`).
4. **Calculation:** pooled overlap-weighted average — House members weighted by `overlap_weight`, senators weight 1.0 each; `p2 = Σ(p×w)/Σw` (`:204-209`). `p2_combined` itself = `key_vote_score×0.60 + inverse_ideology_score×0.40` (precomputed upstream; described `:8-10`).
5. **Weights/thresholds:** 0.60/0.40 (upstream); hostile `< 0.4`, aligned `≥ 0.6` (`thresholds.json:33-34`).
6. **Output:** `p2_national` (aliases `p2_alignment`, `federal_p2`), 0–1. `p2_coverage` ∈ {house_and_senate 2048, house_and_senate_statewide 755, senate_only 184, house_only 114, house_only_statewide 41, unknown 1}.
7. **Discrepancy flags:**
   - `config/weights.json p2_alignment` (lines 94-99) defines P2 as `key_vote 0.60 + inverse_business_funding 0.40` and is marked **"Not yet implemented."** The shipped federal P2 actually uses `inverse_ideology`, **not** business funding. The OpenSecrets/FollowTheMoney campaign-finance rows in the data-source table (`output/index.html:1593-1594`) are **not used** by any live computation found.
   - **P2 is computed for the national lens but then NOT USED by `classify_national`** (P2 dropped from both national pathways, `:268-309`). It is emitted but inert nationally.

### State variant (party)
1. **Where:** `score_p2_state` (`rebuild_state_lens.py:188-205`), called `:287`.
2-7. See **Party ID** input above. `p2_state` (0–1), used by the state-lens classifier and the `state_noncomp_priority` subdivision. **Discrepancy:** party-ID proxy only — no key votes, no finance, despite "alignment" naming.

---

# LENSES & TIERS

## Federal / National lens
1. **Where:** `classify_national` (`build_v2_canonical.py:264-309`), called `:386`. Output `quadrant_national` (also aliased to `quadrant`).
2. **Two Tier-1 pathways, P2 dropped (`:292-300`):**
   - **Capital Tier-1:** `capital_high AND p1_high` → `tier1_capital`. (`capital_high = sls_capital ≥ 2.5`; `p1_high = p1_national ≥ 5.0`.)
   - **Community Tier-1:** `community_high AND swing` → `tier1_community`. (`community_high = sls_community ≥ 25`; `swing = state_tipping_weight ≥ 0.05`.) **No county margin, no county P1** — community's electoral value is purely statewide decisiveness.
   - Both → `tier1_capital_community` (`:295-296`).
3. **Tier cascade (`:303-309`):**
   - `capital_high` but not p1_high → `tier2_build_capital`.
   - `community_high AND lean` (`0.01 ≤ stw < 0.05`) → `tier2_build_community`.
   - else `tier3_electoral` if `p1_high` else `tier4`.
4. **Thresholds (`config/thresholds.json` `quadrant`, lines 29-45):** `sls_capital_high_boundary=2.5`, `sls_community_high_boundary=25`, `p1_high_boundary=5.0`, `state_tipping_swing_floor=0.05`, `state_tipping_lean_floor=0.01`. Mapped into `T` at `build_v2_canonical.py:345-354`.
5. **Output counts (`_tier_counts_national`):** tier4 2696, tier2_build_capital 268, tier3_electoral 72, tier1_community 40, tier1_capital 20, tier2_build_community 46, tier1_capital_community 1.
6. **Discrepancy flags:**
   - National lens **never emits `activate`/`unknown` sublabels** (those require P2, which is dropped) — by construction (`:281-283`).
   - The Community pathway **ignores the county's own presidential margin and `p1_national` entirely** — a community-high county is Tier-1 solely because its *state* is a swing state. A safe-margin county in PA can be Tier-1 community.
   - `sls_community_high_boundary` was recalibrated 35→25 on 2026-06-16 (`thresholds.json:38`); the frontend still hardcodes 35 in two places (see Outputs).

## State lens
1. **Where:** `classify` (`build_v2_canonical.py:234-261`), called from `rebuild_state_lens.py:293` with `T_state`. Output `quadrant_state`.
2. **Both Tier-1 pathways gated by competitive seat + hostile incumbent (`:255-261`):** require `sls_high AND p1_high(state) AND p2_state < 0.4` → `tier1_{dim}` (or `tier1_capital_community` if both SLS dims high). `p1_high = p1_state ≥ 60.0`.
3. **Cascade:**
   - `not sls_high` → `tier3_electoral` if p1_high else `tier4` (`:244-245`).
   - `sls_high AND not p1_high` → `tier2_build_{dim}` (`:251-252`).
   - `sls_high AND p1_high`: `p2 None → tier2_unknown_{dim}`; `p2 < 0.4 → tier1` (Transform); `p2 ≥ 0.6 → tier2_activate_{dim}` (Activate); else `tier2_unknown_{dim}` (neutral) (`:255-261`).
   - `dim = "capital" if capital_high else "community"` (`:249`).
4. **Thresholds:** SLS + P2 identical to national; **only P1 differs** — `p1_high = p1_high_state = 60.0` (`rebuild_state_lens.py:238-244`, from `state_competitiveness` block). Additional `state_noncomp_priority` subdivision of the low-P1 band into hostile/neutral/aligned (`rebuild_state_lens.py:297-306`).
5. **Output counts (`_tier_counts_state`):** tier4 2492, tier2_build_capital 202, tier3_electoral 127, tier2_build_community 197, tier2_activate_capital 49, tier1_capital 21, tier2_unknown_capital 17, tier1_community 14, tier1_capital_community 10, tier2_activate_community 7, tier2_unknown_community 7.
6. **Discrepancy flags:**
   - **The state lens is gated OFF in the UI.** `terrain-map.js:39-41` `setLens()` ignores any `'state'` request and stays national. All `quadrant_state`/`p1_state`/`p2_state` fields are computed and shipped but **never surfaced** (`terrain-map.js:8-10`).
   - The state lens *does* use P2 (party-ID) for the Transform/Activate split, while national does not — the two lenses have asymmetric P2 logic.

---

# OUTPUTS

## The 2×2
1. **Where:** `output/index.html:1057-1071` (`imo-diagram` quad cells); axis semantics in scatter labels `:751-752`.
2. **Axes:** X = **electoral leverage** (P1); Y = **labor leverage** (SLS). Cells:
   - `tier one` — high elec · high labor (`:1061-1063`).
   - `base building` — low elec · high labor (= Tier 2 Build) (`:1057-1059`).
   - `electoral` — high elec · low labor (= Tier 3) (`:1069-1071`).
   - `low prior` — low · low (= Tier 4) (`:1065-1067`).
3. **Discrepancy flags:** the 2×2 collapses the dual-leverage (capital vs community) split and the P2 Transform/Activate axis into a single "labor leverage" Y — a simplification of the actual 6-tier/dual-dimension classifier. It is illustrative, not the live classifier.

## Tier definitions (fields emitted in `county_scores.json`)
Per county (`build_v2_canonical.py:390-422`, plus `rebuild_state_lens.py:308-316`):
`fips, county_name, state, region, population, swing_state, margin_2024,
state_tipping_weight, chamber_tipping_weight, sls_capital, sls_community,
p1_national, p2_national, p1_state, p2_state, p2_coverage, state_p2_coverage,
quadrant_national, quadrant_state, p1_presidential (alias), p2_alignment (alias),
federal_p2 (alias), quadrant (= national alias), p1_state_data_tier, margin_stale,
state_noncomp_priority, v1_* regression fields, _model_version`.
Tier strings: `tier1_capital | tier1_community | tier1_capital_community | tier2_build_{dim} | tier2_activate_{dim} | tier2_unknown_{dim} | tier3_electoral | tier4`.
**Discrepancy:** `quadrant` is a backward-compat alias = `quadrant_national` (`:415`); older JS that reads `quadrant` therefore gets the national value regardless of lens.

## Map — what it colors by
1. **Where:** non-metro counties `getGoalFill` (`terrain-map.js:466-478`, render `:828-831`); metro/MSA `getMsaGoalFill` (`:486-499`, render `:780-784`). `goalFilter` locked to `"power"` (`:32`).
2. **Non-metro path:** `QUADRANT_COLORS[getLensQuadrant(c)]`. `getLensQuadrant` returns `quadrant_national` = a `tier*` string (`:51-54`). But `QUADRANT_COLORS` (`:395-403`) is keyed **only by legacy names** (`deploy_now_*`, `primary_target_*`, `power_building`, `lower_priority`) — it has **no `tier*` keys**. So every non-metro county → `undefined` → `NO_DATA_COLOR` (`#EDEAE3`).
3. **Metro path:** `QUADRANT_COLORS[msa.dominantQuadrant]`. `dominantQuadrant` comes from `classifyMsaQuadrant` (`:605-616`), an **independent JS re-classification** that returns the legacy strings (so it DOES color) — but it uses **stale/divergent logic**: `sls_community ≥ 35` (config is 25), community Tier-1 keyed on `p1_presidential ≥ 5` (the national lens uses `state_tipping_weight` swing gate, not county P1), no P2, no two-pathway model, population-weighted MSA averages.
4. **CONFIRMED MAP-COLOR BUG (suspected bug, reported not fixed):**
   - **Non-metro counties do not render their tier color at all** — they all fall through to no-data gray because `QUADRANT_COLORS` lacks the `tier*` keys the data now uses.
   - **Metro areas render a *different, older* classification** (`classifyMsaQuadrant`) than the canonical `quadrant_national`, with a stale community threshold (35 vs 25) and presidential-margin gating instead of swing-state gating. The map fill does **not** faithfully reflect `quadrant_national`.
   - Note the scatter and tooltips DO handle `tier*` correctly (`index.html:2146-2153` `tierColor`; `terrain-map.js:155-164` `_tierNum`/`_TIER_LABELS`), so labels/scatter and map-fill disagree.

## Scatter — axes and Y choice
1. **Where:** `output/index.html:2170-2203` (`render`).
2. **Data filter:** counties with `sls_capital != null AND (p1_national != null OR p1_presidential != null)` (`:2172-2174`).
3. **Axes (percentile-indexed 0–100, `pctRanks` `:2155-2161`):**
   - **X = electoral leverage** = percentile rank of `p1_national` (fallback `p1_presidential`) (`:2176`, `:2186`).
   - **Y = labor leverage** = `Math.max(capP[i], commP[i])` — the max of the county's capital-percentile and community-percentile (`:2185`), inverted so high labor is near the top (`:2187`).
4. **Color:** `tierColor(quadrant_national)` (`:2188`, `:2196`) — correctly maps `tier*` → hex (tier1 cap `#BD0026` / comm `#1a3a6b`, tier2 `#E8736B`/`#4A7FB5`, tier3 `#7B6B9E`, tier4 `#E0DBD3`).
5. **Leverage type per dot** = `capP[i] >= commP[i] ? capital : community` (`:2192`), used by the highlight engine.
6. **Discrepancy flags:**
   - **Y = max(capital pct, community pct)** mixes the two different-scale leverages into one percentile axis — the code itself flags this as a "known blur" (`:2183-2184`). A county can be high-Y from either dimension; the axis does not say which.
   - X uses `p1_national`, the presidential leverage — but national Community Tier-1 is gated on `state_tipping_weight`, not `p1_national`, so a Tier-1-community dot can sit at low X yet be colored Tier 1 (axis/color mismatch by construction).
   - Swing-7 set is hardcoded `{PA,MI,WI,AZ,GA,NV,NC}` (`:2165`) with a `TODO(config)` note.

---

# CROSS-CUTTING LISTS

## Data source paths / URLs (for hyperlinking)
- County employment: `data/processed/county_sector_employment.json` (Census CBP 2023; BLS QCEW public-sector). 
- Sector reach rubric: `data/processed/sector_reach_scores.json` (Notion DB; NAICS).
- Vote margin: `margin_2024` carried via `data/county_scores_v2_test.json` ← Notion "Presidential 2024 Margin" ← MIT Election Data & Science Lab, 2024.
- Presidential tipping: `data/state_tipping_weights.json` (538, 2024 cycle).
- Chamber tipping / seat counts: `data/processed/chamber_seat_counts.json` (NCSL, 2024 results; `_vintage 2025`).
- Federal P2 (key votes + ideology): `config/key_votes.json`, `data/processed/federal_key_vote_scores.csv`, `data/processed/federal_ideology_scores.csv` → `data/processed/federal_p2_combined.csv` (House Clerk XML / Congress.gov / Senate.gov; GovTrack 119th; DIME CFscores).
- District→county crosswalk: `data/processed/district_county_crosswalk.csv` (Census District Relationship Files, decennial).
- State P2 (party ID): `data/work_stateleg/county_seat_detail.json` (Open States) + `data/processed/state_p2_county_alignment.csv`.
- State-leg competitiveness: `data/processed/state_leg_competitiveness.csv` (+ `_backfill.csv`) (MEDSL SLERs 1967-2022; gubernatorial/state-returns overlay).
- Key-vote source URLs: `config/key_votes.json _data_sources` (clerk.house.gov, api.congress.gov, senate.gov).
- Listed-but-unused: OpenSecrets, FollowTheMoney (campaign finance) — in the index data-source table (`output/index.html:1593-1594`) but not consumed by any live computation found.

## Hardcoded values that bypass config (single-source-of-truth violations)
- `_NORM = 100.0/0.28` national P1 normalization — hardcoded `build_v2_canonical.py:41` (and duplicated `scoring/electoral.py:44`), derived from PA's tipping value; not config-read.
- Community `share_score = weighted × 4` — multiplier hardcoded `build_v2_canonical.py:111`.
- National-P1 null-margin default `15.0` hardcoded `build_v2_canonical.py:119` (mirrors `electoral.py:47`; `thresholds.json` has separate legacy `null_margin_default` values that are unrelated).
- Frontend `capitalHigh = 2.5`, **`communityHigh = 35`**, `p1High = 5` hardcoded in `getCountyNarrative` (`terrain-map.js:216-218`) and `classifyMsaQuadrant` (`:606-608`) — the community value (35) is **stale** vs config 25.
- Swing-state sets hardcoded in three places: `terrain-map.js:393` `SWING_STATES_PRES {PA,WI,MI,AZ,GA,NV,NC}`, `index.html:2165` `SWING7`, and `thresholds.json:60` `swing_states_presidential` (the canonical list) — three copies, with a documented NC display inconsistency note (`thresholds.json:62`).
- Senate-race tiers `SENATE_TIERS`/`SENATE_TIER_COLORS` hardcoded `terrain-map.js:429-437` (unrelated to scoring, display-only).

## Map-color bug (summary — reported, not fixed)
- **Non-metro counties:** colored by `quadrant_national` (`tier*`) via `QUADRANT_COLORS`, which has no `tier*` keys → all render `NO_DATA_COLOR` gray. (`terrain-map.js:395-403, 466-478, 828-831`.)
- **Metro areas:** colored by a separate, **stale** JS classifier `classifyMsaQuadrant` (community threshold 35 not 25; presidential-margin gate not swing-state gate; no P2) — diverges from the canonical `quadrant_national`. (`terrain-map.js:605-616`.)
- The map fill therefore does NOT match the emitted tier definitions; the scatter and tooltips (which handle `tier*`) do.

## Scatter (summary)
- X = `p1_national` percentile (electoral leverage); Y = `max(capital percentile, community percentile)` (labor leverage), inverted; color = `quadrant_national` tier hex. The `max()` blends two different-scale leverages — self-flagged as a "known blur" (`index.html:2183-2185`).
