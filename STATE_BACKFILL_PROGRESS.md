# Targeted State-Returns Backfill — Progress & Coverage (Agent 5)

**Branch:** `state-returns-backfill` · best-effort data task · OVERLAY only (does not touch base file or scoring)
**Output:** `data/processed/state_leg_competitiveness_backfill.csv` (same schema as base; only counties genuinely upgraded above the presidential floor)

Margin convention (matches base + `county_scores.json`): **D − R %, positive = Democratic advantage.** `competitive = |margin| ≤ 3`.

---

## Target set (confirmed against Agent 2's `STATE_MARGINS_PROGRESS.md` coverage table)

Agent 2's table shows which states fall to the **presidential floor** (Tier C). The overlay rule is: only replace presidential-floor counties with a genuinely higher-confidence state-level signal. So the real target set = states with a meaningful presidential-tier share:

| State | pres-tier counties (Agent 2) | Plan | Priority |
|---|---|---|---|
| VA | 133 (all) | 2021 gubernatorial county returns (2023 state-leg has no clean county crosswalk) | 1 |
| NJ | 21 (all) | 2021 gubernatorial county returns | 1 |
| MS | 82 (all) | 2023 gubernatorial county returns | 1 |
| LA | 64 (all) | 2023 gubernatorial (jungle-primary Oct 2023) county returns | 3 |
| NE | 93 (all) | 2022 gubernatorial county returns | 3 |
| CT | 9 (all) | 2022 gubernatorial — STRETCH (FIPS planning-region remap from town returns) | 2 |
| VT | 14 (all) | 2022 gubernatorial — CAUTION: popular-incumbent (Scott R) blowout is a poor state-competitiveness signal in a deep-blue state | 2 |
| MA/MT/ND/SD | 6/2/1/6 partial | skip — tiny partial floors, low value | — |

**Priority-2 split-ticket states named in the brief (KS, KY, MT, WV, NH, NC): NOT targeted.**
Agent 2's coverage table shows these are already ~100% Tier A `district_actual` (KS 0 pres, KY 0 pres, WV 0 pres, NH 0 pres, NC 0 pres, MT 2 pres). They are NOT on the presidential floor, so a gubernatorial overlay would *replace a real district margin with a statewide one* — a tier downgrade, which violates the overlay rule. Documented here; left untouched.

---

## RESULT — 393 counties upgraded off the presidential floor → `gubernatorial`

All 5 obtainable target states delivered. Every overlay row was verified to (a) exist in the base file and (b) have been on the `presidential` floor there — i.e. every row is a genuine upgrade. Each state's statewide margin reconstructed from the county data matches the published statewide result (sanity check passed). Build is fully reproducible end-to-end: `python3 scripts/build_state_returns_backfill.py` re-downloads every source and regenerates a byte-identical CSV.

| State | race used | vintage | counties | competitive (\|m\|≤3) | source | statewide check |
|---|---|---|---:|---:|---|---|
| VA | gubernatorial | 2021 | 133/133 | 5 | official VA Dept of Elections precinct CSV → locality | reconstructed −1.94% vs actual ~R+1.9 ✓ |
| NJ | gubernatorial | **2025** | 21/21 | 1 (Morris +2.21) | official NJ Div. of Elections statewide results PDF | D/R totals exact (1,896,610 / 1,417,705); +14.36% ✓ |
| MS | gubernatorial | 2023 | 82/82 | 7 | OpenElections county CSV | −3.42% vs actual ~R+3.3 ✓ |
| LA | gubernatorial open primary | 2023 | 64/64 | 0 | official LA SoS "Human Readable" Excel | matches certified parish totals ✓ |
| NE | gubernatorial | 2022 | 93/93 | 0 | official NE Board of State Canvassers canvass book PDF | D/R totals exact (242,006 / 398,334); −23.24% ✓ |

**Per-state notes:**
- **MS** — Presley (D) vs Reeves (R) + Ind. Gray (Gray kept in the denominator). 7 competitive counties — exactly the split-ticket signal the brief was after (e.g. Attala, Madison, Montgomery flip more competitive at the state level than their presidential margins).
- **NJ** — used the **most-recent (Nov 2025)** race per the brief. Parsed the official statewide-summary PDF (county tallies per candidate); minor parties (Libertarian, Socialist Workers) kept in the denominator.
- **VA** — used **2021** gubernatorial, NOT the most-recent 2025. The 2025 race is **not cleanly machine-readable** (see NEEDS SAM #1); 2021 is the most recent clean state-level signal and is itself a near-tie (R+1.9) that diverges sharply from VA's presidential lean — high-value. Liberation Party + write-ins kept in the denominator.
- **LA** — 2023 open ("jungle") primary, 15 candidates; margin = (ΣDEM − ΣREP)/total. **Coarser** than a head-to-head (R vote is fragmented across many candidates); still real official state-level returns and strictly better than the presidential floor. Sam may want to eyeball whether the gubernatorial `competitive` band should differ for jungle-primary states.
- **NE** — nonpartisan-unicameral state, so gubernatorial is the only partisan statewide signal; Pillen (R) vs Blood (D) + Libertarian + write-ins in denominator.

**Competitive-band note for Sam:** kept the base definition `competitive = |margin| ≤ 3`. For gubernatorial (especially LA's jungle primary and incumbent blowouts) you may want a different band; flagging per the brief.

## NEEDS SAM

1. **VA 2025 gubernatorial — recommend manual refresh later.** I delivered VA on **2021** gov, not the most-recent 2025 (Spanberger D def. Earle-Sears R, ~D+15). 2025 is genuinely hard to obtain cleanly in machine-readable form right now:
   - VA's live ENR portal (`enr.elections.virginia.gov`) is an Angular SPA over `/results/public/api`. I fully reverse-engineered its routes (`/elections/{jurisdiction}/{election}` + `/localities`, `/stats`, `/turnout`, `/vr`). The locality and stats endpoints return **turnout/metadata only — `contestGroups` is empty for every election** (confirmed on both 2024 and 2025), so candidate/contest vote data is not exposed through any reachable public endpoint; GraphQL introspection is disabled.
   - VA's official bulk CSV repo (`apps.elections.virginia.gov/SBE_CSV/ELECTIONS/ELECTIONRESULTS/`) **lags — latest folder is 2023.** When a `2025/` folder appears (or a `2025 November General .csv`), swap `ingest_va()` in `scripts/build_state_returns_backfill.py` to that file (same precinct→locality aggregation already written) and re-run. VA boundaries (FIPS) are stable, so no remap needed.

2. **Whole states still on the presidential floor that I deliberately did NOT touch** (out of scope or no clean state-level signal):
   - **CT (9 planning regions):** worth a future backfill via **2022 gubernatorial town returns → planning-region rollup** (CT reports by town; towns map cleanly into the new planning regions, which is exactly the join Agent 2 avoided). I scoped but did not build this — it needs a town→planning-region crosswalk. Good NEEDS-SAM candidate.
   - **VT (14):** most-recent gov is 2024 (Scott R, ~+40 in a deep-blue presidential state). A popular-incumbent blowout is a **poor state-competitiveness signal** — I judged it more misleading than the presidential floor and left it. Your call.
   - **DC (1):** no partisan gubernatorial race — nothing to add.
   - **MA (6 floored), MT (2), ND (1), SD (6):** only small *partial* presidential remnants (the rest are already Tier A `district_actual`). Low value; skipped.

3. **Priority-2 split-ticket states named in the brief (KS, KY, MT, WV, NH, NC) — intentionally NOT overlaid.** Agent 2's coverage table shows these are already ~100% Tier A `district_actual` (real state-leg district margins), not on the presidential floor. Overlaying a statewide gubernatorial margin would *downgrade* a real district-level signal, violating the overlay rule ("genuinely higher-confidence than the presidential floor it replaces"). If you ever want gubernatorial as an *alternative* lens for these (rather than a replacement), that's a separate design decision — not a floor backfill.

## How the overlay folds in
Agent 1's build replaces base rows by `fips` with overlay rows. All 393 overlay `fips` were validated to exist in the base and to have been `presidential` tier; headers are byte-identical to the base schema. No formula change needed — re-run Agent 1's build after merge.

## Reproduce
`python3 scripts/build_state_returns_backfill.py` — re-downloads all 5 sources into `data/work_state_returns/` (gitignored) and writes `data/processed/state_leg_competitiveness_backfill.csv`. Requires `openpyxl` + `pypdf`.

## Build-time guards (persist on every re-run)

**1. Validation — `validate()` runs BEFORE the CSV is written and fails loudly (`raise SystemExit(1)`, non-zero exit) so a bad re-run cannot silently overwrite a good file.** Hard checks (any failure aborts):
- every county margin finite (no None/NaN) and within `[-100, +100]`; every `fips` is a canonical FIPS;
- per-state county counts exact: VA 133, NJ 21, MS 82, LA 64, NE 93 (`EXPECTED_COUNTS`);
- vote-weighted statewide aggregate reconciles to the verified certified margin within **±2 pts** (`EXPECTED_STATEWIDE` = VA −1.94, NJ +14.36, MS −3.42, LA −36.98, NE −23.24);
- LA-specific (jungle-primary margin is coarse): distribution not degenerate — both signs present and spread ≥ 20 pts; logs LA min/median/max/spread for eyeball review.

Soft check (warn, never fails): any county whose margin deviates from its state mean by > **45 pts** (`OUTLIER_THRESHOLD`) is logged `[outlier:review]`. On the current data these are all legitimate D strongholds (cities / Black-belt / tribal counties) vs R-rural — expected, not errors. Last run printed **VALIDATION: PASS**, and the fail path is unit-confirmed to exit 1.

**2. VA 2025 swap readiness.** `ingest_va()` reads from a single constant `VA_ACTIVE_URL` (currently `VA_2021_URL`), with `VA_2025_URL` defined alongside and a 3-line swap checklist in the comment (URL → SPECS vintage → `EXPECTED_STATEWIDE['VA']`). `check_va_2025_availability()` probes the VA bulk-CSV repo's 2025 path on every build and logs whether it's live yet (currently non-200 → stays on 2021). VA stays on 2021 until 2025 is cleanly obtainable.
