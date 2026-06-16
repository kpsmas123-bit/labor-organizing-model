# STATE-LENS REBUILD — Progress & Decisions (Agent 1)

Branch: `state-lens-rebuild` (from `main` after Phase 0 merges). **Do NOT merge. State lens stays HIDDEN.**

## NEEDS SAM (top — review before un-gating)
1. **`p1_high_state = 30.0` threshold.** Chosen to make the state lens selective (289 counties / 9.2% high-P1,
   vs ~56% under the broken P1; national high-P1 is ~3%). It is a *different scale* from national P1 by design
   (see P1 section). If you want the state lens tighter/looser, this single number is the knob — every tier
   count below moves with it.
2. **BAND = 8.0pp** for the competitiveness signal. Widened from the ~3% "competitive" convention to get
   gradation (at 3pp only 6% of counties get any signal; at 8pp, 13%). Tunable.
3. **`organized_scale_score` gone in v2** (Phase 1 side-effect): jobs.html MSA `infraScale` tiebreaker degraded
   to 0. Pick a v2 infra field (SLS?) if you want that tiebreaker live.
4. **DC + DE (4 counties)** have no chamber data in `chamber_seat_counts.json` → `p1_state = 0` (floor). DC P2
   also unavailable → `p2_state = 0.5` neutral, `state_p2_coverage = party_proxy_unavailable`. Same 4-county
   gap the original build flagged.
5. **194 counties** could not resolve party from district overlap → `p2_state` fell back to the state-uniform
   legislative Dem share, flagged `state_p2_coverage = party_proxy_state_uniform`. List in
   `data/work_stateleg/state_lens_rebuild_log.json`.

## Phase 0 (merges) — done, see MERGE_LOG.md
Both PRs merged to main cleanly (no conflicts); pushed. v2 dual-lens `county_scores.json` + Agent 2 data now canonical.

## Phase 1 (jobs.html v2) — done, pushed to main
`computeMsaData()` now reconstructs MSA grouping from `data/msa_lookup.json` (fips→MSA) since v2 has no
`msa_name`; mapped `v1_organizing_opportunity_score` / `v1_intervention_type`. Verified: 925 MSAs, 0 console
errors, panel renders. (Unrelated `jobs.html` SVS-removal WIP left in `git stash@{0}` for Sam.)

## Phase 2 — state-lens rebuild

### Inputs (Step 0)
- `data/processed/state_leg_competitiveness.csv` — 3,144 rows; per-county `margin` already aggregated to the
  **most-competitive seat the county touches** (kept that rule). `p1_data_tier` = district_actual (2,712) /
  presidential (432). `margin_stale` True for 147.
- `data/work_stateleg/county_seat_detail.json` — per-county list of districts with `current_party`, `share`
  (overlap weight), `margin`, `stale`. Source of P2 (and a cross-check on P1).
- `data/processed/chamber_seat_counts.json` — `tipping_weights['<ST>_house'/'<ST>_senate']` =
  `1 − seats_from_flip/total_seats` (near-tie → ~1.0). 49 states (no DC; **DE absent**; NE = senate only).
- **Overlay:** `state_leg_competitiveness_backfill.csv` checked for and NOT present (Agent 5 not merged). The
  build auto-applies it (overlay rows replace base by fips) on a future re-run with zero code change.

### Step 1 — P2_state (party proxy, county-resolved)
`P2_state = Σ(share | current_party=D) / Σ(share | current_party∈{D,R,I})`, from the CURRENT roster in
`county_seat_detail.json`. 0 = all-R (hostile), 1 = all-D (aligned); same 0–1 scale as federal P2, so the
existing hostile<0.4 / aligned≥0.6 cut points apply unchanged. `None`-party seats excluded from the
denominator (unknown); Independents count toward the denominator but not the Dem numerator. Fallbacks: zero
overlap → state-uniform legislative Dem share (194 counties, flagged); no chamber data at all → 0.5 neutral
(DC only, flagged). `state_p2_coverage = party_proxy` on every resolved county.

### Step 2 — P1_state (competitiveness × chamber-flip proximity) — THE RECALIBRATION
`P1_state = 100 × chamber_flip_proximity × comp(margin)` where
`comp(margin) = max(0, (BAND − |margin|)/BAND)`, BAND = 8.0pp (peaks 1.0 at margin 0, → 0 at ±8pp; **no
1/margin**). `chamber_flip_proximity = tipping_weights[<state>_<chamber of the most-competitive seat>]`
(chamber parsed from the competitiveness `source` "seat=AL-L069" → L=house/U=senate). Presidential-tier /
unnamed-seat counties use the state-mean chamber proximity; DC/DE (no chamber data) floor to 0.
`p1_state_data_tier` carried from the competitiveness `p1_data_tier`; `margin_stale` carried through.
**Selectivity:** 289 counties (9.2%) ≥ `p1_high_state` (30.0), vs ~56% before.

### Step 3 — classifier + the one enhancement
Reused the EXISTING `classify()` from `build_v2_canonical.py` unchanged, with a state-specific threshold
dict (`T_state['p1'] = p1_high_state = 30.0`; SLS + P2 thresholds identical to national). Quadrant strings
identical to national. **Enhancement:** added `state_noncomp_priority` ∈ {hostile, neutral, aligned} for the
NON-competitive (low-P1) band only (null for high-P1) — additive, does NOT alter `quadrant_state`. Encodes
Sam's medium/low distinction so a non-competitive **hostile** county outranks a non-competitive **aligned**
one. Low-P1 split: hostile 2,415 · neutral 154 · aligned 285.

### Step 4 — county reconciliation (3,143 vs 3,144)
Canonical `county_scores.json` (3,143) is ground truth. All 3,143 join to both competitiveness and
seat-detail. The one extra competitiveness/seat-detail row — **FIPS 15005 (Kalawao, HI)** — is NOT canonical;
**logged, not force-fit**. Zero canonical counties missing competitiveness data.

### Step 5 — output
`pipeline/rebuild_state_lens.py --write` updated ONLY `p1_state`, `p2_state`, `quadrant_state`,
`state_p2_coverage`, `p1_state_data_tier`, `margin_stale`, `state_noncomp_priority`. Backup:
`data/archive/county_scores_pre_state_lens_rebuild.json`. **National fields + SLS verified identical across
all 3,143 counties (0 diffs).** Log: `data/work_stateleg/state_lens_rebuild_log.json`.

### Step 6 — distribution + spot-checks
**New state tiers:** Tier1 = 42 (cap 33 / comm 8 / both 1) · Tier2 = 545 (build 461 / activate 60 / unknown 24)
· Tier3 = 163 · Tier4 = 2,393.  **Was:** Tier1 = 141 · Tier3 = 1,775 · Tier4 = 781.

Hand spot-checks (P1, P2, quadrant all reproduce):
- **Competitive/hostile** — Aleutians East Borough, AK (02013): margin 0 → comp 1.0 × prox 0.925 = **P1 92.5**;
  P2 0.0 (all-R, hostile); low SLS → **tier3_electoral**.
- **Competitive/aligned** — Bethel Census Area, AK (02050): **P1 92.5**; P2 0.763 (aligned); SLS-comm 51 (high)
  → **tier2_activate_community**.
- **Safe** — Barbour County, AL (01005): margin 81 → comp 0 → **P1 0.0**; low SLS → **tier4**
  (`state_noncomp_priority = aligned`, P2 1.0).

### Gating
Agent 3's gating untouched — dashboard line ~690 still hides the toggle; lens forced to national. **Not un-gated.**
