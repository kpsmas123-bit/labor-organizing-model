# BUILD_PROGRESS — Terrain v2.0 (real P2 + dual lens + site rewire)

Branch: `v2-build-real-p2-dual-lens`. Unattended run. Every non-trivial decision logged here.

---

## NEEDS SAM (read first)

1. **State-lens P1 normalization / scale.** The published methodology (methodology.html L1091–1095) says the State lens uses the *same* P1 formula `state_tipping_weight × (1/abs(margin))` with **chamber tipping weights substituted** for presidential tipping weights. But the two weight families live on different scales: presidential tipping weights are decisive-state probabilities (0.005–0.28), while chamber tipping weights (`1 − seats_from_flip/total_seats`) run ~0.5–0.95. Reusing the presidential normalization constant (×357.14 = 100/0.28) is therefore literally what the spec says, but it makes state-lens P1 margin-dominated and pushes many competitive-margin counties to the 100 cap. **I implemented the literal spec (same formula, same NORM, chamber weight substituted) and did NOT invent a new constant.** If you want state-lens P1 spread out more, recalibrate a state-lens NORM. Distribution is reported under Step 4.

2. **State-P2 three-tier provenance not available in source.** Step 3 asks for a per-county `state_p2_coverage` of `dime_matched` / `party_imputed` / `state_keyvote`. The actual source file `data/processed/state_p2_county_alignment.csv` carries a SINGLE coverage value for every row: `cfscore_plus_imputed` (DIME CFscores + party imputation already blended at the state level). The per-county three-way split is not recoverable from this file. I carry the real provenance the file provides (`cfscore_plus_imputed`) as `state_p2_coverage`, and mark DC (no legislature) separately. No silent fallback to federal proxy occurs.

3. **DC and DE state-lens gaps.** DC (11001) has no state legislature → no chamber tipping, no state P2: `p1_state=null`, `p2_state=null`, flagged. DE has no rows in `chamber_seat_counts.json` → `p1_state=null` (state P2 still present via state_p2 file). Both honest nulls, neither dropped from the county set. (Confirmed in output: exactly 4 counties have `p1_state=null` = DC's 1 + DE's 3.)

4. **jobs.html MSA panel needs `msa_name` — absent from v2 schema.** The MSA list in `output/jobs.html` (`computeMsaData`) keys on `c.msa_name`, which **does not exist in `county_scores.json` (neither v1 nor v2)**. It also wants `organizing_opportunity_score` / `intervention_type` / `organized_scale_score`, none of which are in v2 (v2 has only `v1_organizing_opportunity_score`, `v1_intervention_type`; no organized-scale field at all). I fixed what Step 9 instructed — the silent data-shape bug (v2 is `{counties:[…]}`, not a bare array, so the loader was returning early), `state_abbr`→`state`, `organized_scale`→`organized_scale_score` — and the page now loads with **zero JS errors**, but the MSA list is still empty because `msa_name` is genuinely missing. The MAP page solves this by merging `msa_name` from a separate Census CBSA lookup (`data/msa_lookup.json`) by FIPS. **Decision for Sam:** either (a) have jobs.html do the same FIPS→msa_name merge, or (b) add `msa_name` (+ an `organized_scale_score`) to the canonical build. I did not invent either, per instructions.

---

## STEP 0 — Build path + inventory (CONFIRMED)

- **Real build script:** `pipeline/build_v2_scores_true.py` → writes `data/county_scores_v2_test.json`, never overwrites `county_scores.json`. Confirmed (L7–9, L342). I am NOT editing scoring/ modules; I authored a NEW canonical build script `pipeline/build_v2_canonical.py` (non-destructive; original preserved for audit) that produces the full v2.0 schema.
- All required inputs exist:
  - `data/processed/federal_p2_combined.csv` — 365 members, cols include `key_vote_score, inverse_ideology_score, p2_combined, coverage_type`. **`p2_combined` already = key_vote_score×0.60 + inverse_ideology_score×0.40** (verified to 6dp on row 0). Feinstein ABSENT from this file. 50 states, 277 house + 88 senate.
  - `federal_key_vote_scores.csv`, `federal_ideology_scores.csv` — intermediates. Feinstein present in key_vote_scores (intermediate only) — excluded because I aggregate from `federal_p2_combined.csv`, which already drops her.
  - `state_p2_county_alignment.csv` — 3,142 rows, **uniform score per state** (all 50 states single value), coverage uniformly `cfscore_plus_imputed`.
  - `chamber_seat_counts.json` — 97 chambers across 49 states (CT present; DC & DE absent).
  - `state_tipping_weights.json` — presidential, `_default=0.005`.
  - `district_county_crosswalk.csv` — 3,838 pairs (`district_state` FIPS2, `district_number` zero-padded, `county_fips`, `overlap_weight`).
  - `config/weights.json` (has p2_alignment 0.60/0.40), `config/thresholds.json` (quadrant thresholds present; **NO p2 cut points — to be ADDED**).

## STEP 1 — CT / FIPS reconciliation (RESOLVED)

- **Master county list = the employment file keys: 3,143 counties.** CT uses the NEW 9 planning-region FIPS (091x0). The existing v2_test also uses 091x0 and contains DC (11001) but NOT Kalawao (15005). **Chosen scheme: NEW CT planning regions (091x0).** It joins cleanly across the two largest/most-authoritative inputs (employment master + existing SLS/P1 carrier).
- `state_p2_county_alignment.csv` and `district_county_crosswalk.csv` use OLD CT county FIPS (0900x). Reconciliation:
  - **State P2 needs no FIPS join** — scores are state-uniform, so every CT planning region simply inherits CT's state value (0.5339). Trivially robust.
  - **Federal P2** aggregates via the crosswalk (OLD CT FIPS) → CT's 9 new-FIPS counties find no House districts. Fallback: assign them the statewide pooled federal average (all CT House + Senate members), coverage-flagged `house_and_senate_statewide`. Preserves House signal without inventing geography. Same fallback applies to any master county the crosswalk misses.
- DC (11001): no federal voting reps (0 rows) → `p2_national=null`; no chamber/state legislature → `p1_state=null`, `p2_state=null`.
- Kalawao (15005): not in master employment list → naturally excluded; consistent with the 3,143 count. No county dropped.
- **Final county count: 3,143** (matches Session 2's published figure).

## BUG #1 (Step 6) — confirmed and fix chosen

LA (06037, CA non-swing): stored `state_tipping_weight=0.0` but stored `p1_presidential=0.05`, which reproduces only at weight **0.005** (the `_default`), not 0.0. **Fix: use `_default=0.005` BOTH as the stored `state_tipping_weight` and in the national P1 computation** for states absent from `state_tipping_weights.json`. Swing states unaffected (they carry explicit weights). National P1 is recomputed fresh (not carried) so stored weight and P1 are always consistent.

## Employment metadata bug (Step 7)

`county_sector_employment.json` `_count=101917` but true sector-county entry count = **65,917** (3,143 counties). Will correct `_count` to 65917.

---

## DECISIONS LOG (running)

- Federal P2 county aggregation: pooled weighted average of `p2_combined` over each county's House members (weight = district `overlap_weight`) plus both state Senators (weight = 1.0 each). Coverage: `house_and_senate` if any house overlap, else `senate_only`, else `house_and_senate_statewide` (crosswalk-miss fallback), else `unknown`.
- State-lens chamber tipping weight per state: **average** of that state's chamber tipping weights (senate + house; unicameral NE = its single chamber). Logged as a revisitable modeling choice.

---

## CLOSE-OUT (final, verified)

**Final county count:** 3,143 · **errors:** 0 · **model_version:** 2.0 · canonical file: `data/county_scores.json` (v1 backed up to `data/archive/county_scores_v1_2026-05-17.json`).

**Canonical field names (per county):** `sls_capital, sls_community, p1_national, p2_national, p1_state, p2_state, p2_coverage, state_p2_coverage, quadrant_national, quadrant_state, state_tipping_weight, chamber_tipping_weight, margin_2024` + identity (`fips, county_name, state, region, population, swing_state`) + v1 regression fields. Backward-compat aliases kept for older JS: `p1_presidential`=p1_national, `p2_alignment`=federal_p2=p2_national, `quadrant`=quadrant_national.

**Sanity checks (filtered reads, all passed):**
- National "clear all three thresholds" (capital≥2.5 ∧ community≥35 ∧ p1_national≥5) = **0** ✓ (deploy_now_both empirical finding holds). State lens = 9 (different P1 basis, expected).
- 3 hand spot-checks reproduced exactly: LA 06037 (p1_nat 0.05, p1_state 7.73, p2_nat 0.918, nat=tier2_build_capital, state=tier2_unknown_capital); Philadelphia 42101 (both SLS high, nat=tier2_build_capital); Centre 42027 (p1_nat 35.34 reproduces old value, nat=tier3_electoral).
- BUG #1 fixed: LA now stores `state_tipping_weight=0.005` consistent with `p1_national=0.05`.

**National tier counts:** tier1_capital 7, tier1_community 14, tier1_capital_community 0 → **Tier 1 national = 21** (old hardcoded headline was 36; map now reads it live + static fallback updated to 21). tier2_activate_capital 7, tier2_activate_community 1, tier2_build_capital 278, tier2_build_community 273, tier2_unknown_capital 7, tier3_electoral 59, tier4 2497.

**State tier counts:** tier1_capital 98, tier1_community 41, tier1_capital_community 2 (**Tier 1 state = 141**), tier2_activate_capital 11, tier2_build_capital 14, tier2_build_community 145, tier2_unknown_capital 174, tier2_unknown_community 102, tier3_electoral 1775, tier4 781. (State lens is high-P1-heavy — see NEEDS SAM #1 on chamber-weight scale.)

**Federal P2 coverage breakdown (national, n=3,143):** house_and_senate 2048, house_and_senate_statewide 755, senate_only 184, house_only 114, house_only_statewide 41, unknown 1 (DC). Statewide-fallback counts reflect gaps in the federal source file (missing some House districts incl. AL-02/redraws, and 12 missing Senators across some states) — handled honestly via coverage flags, never dropped.

**State P2 coverage breakdown:** cfscore_plus_imputed 3,142 · no_state_legislature 1 (DC). (Source carries one blended coverage type — see NEEDS SAM #2.)

**Frontend verification (served via local http, real fetch):** map loads 3,143 counties, **0 JS console errors**; lens toggle now genuinely changes the map (national Tier1=21/Tier3=59 → state Tier1=141/Tier3=1,775 — previously a cosmetic no-op); info card shows lens-appropriate P2 label + coverage flag; `finding-tier1` headline computes live to 21. jobs.html loads with 0 errors (MSA list empty per NEEDS SAM #4).

**Steps done:** 0–10 all complete. Step 10: `scoring/sls.py` marked DEPRECATED via header (dead code, wrong denominator 100k vs 210k, wrong community formula) — not imported by the real build.

**New/edited files:** `pipeline/build_v2_canonical.py` (new canonical build; original `build_v2_scores_true.py` left intact for audit), `config/thresholds.json` (added p2 cut points), `data/county_scores.json` (now v2 canonical), `data/processed/county_sector_employment.json` (`_count` 101917→65917), `output/labor_organizing_national_dashboard.html`, `output/jobs.html`, `scoring/sls.py`, `STATUS_V2.md`.
