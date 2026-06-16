## What this does (plain English)

The live model was internally correct but **incomplete** — the upper half of v2.0
(real P2 alignment + the National/State dual lens + the 6-tier classification) had
been built as data files but never wired into the build. This PR wires it in and
makes the model match the published methodology. **The live site is untouched until
you merge — that's the safety net.**

## ⚠️ NEEDS SAM — read before merging (full detail in `BUILD_PROGRESS.md`)

1. **State-lens P1 scale.** The methodology says the State lens reuses the *same* P1
   formula with chamber tipping weights swapped in for presidential ones. Those two
   weight families are on different scales (presidential 0.005–0.28 vs chamber ~0.5–0.95),
   so reusing the same normalization makes state-lens P1 margin-dominated and pushes many
   competitive counties to the 100 cap. I implemented the **literal spec** and did **not**
   invent a new constant. If you want state-lens P1 spread out, we add a state-lens NORM.
2. **State-P2 provenance is one blended tier, not three.** The source file carries a single
   `cfscore_plus_imputed` coverage value per county (DIME + party imputation already blended),
   not the `dime_matched`/`party_imputed`/`state_keyvote` split. I carry the real value the
   file provides. No silent fallback to the federal proxy ever happens.
3. **DC + DE have no state lens** (4 counties): DC has no legislature, DE isn't in the chamber
   seat file → `p1_state`/`p2_state` are honest nulls. Nothing dropped.
4. **jobs.html MSA panel needs `msa_name`**, which doesn't exist in the county schema (never did).
   I fixed the silent data-shape bug + the field-name mismatches you flagged, so the page now
   loads with zero errors, but the MSA list stays empty until `msa_name` is supplied (the map
   page merges it from a separate CBSA lookup — we can do the same here, your call).

## What changed

**Scoring** (`pipeline/build_v2_canonical.py` — new; original `build_v2_scores_true.py` left intact):
- **Real federal P2** = `key_vote × 0.60 + inverse_ideology × 0.40`, aggregated to county by
  congressional-district overlap. Dianne Feinstein (d. 2023) is excluded.
- **Real state P2** from DIME + party-imputed alignment, with explicit per-county coverage flags.
- **Dual lens**: National (presidential tipping + federal P2) and State (chamber tipping + state P2).
  SLS is identical in both; only P1 and P2 change.
- **6-tier classification** run once per lens → `quadrant_national` and `quadrant_state`.
- **BUG #1 fixed**: non-swing states now store a tipping weight consistent with their P1 (0.005).
- CT reconciled onto the new planning-region FIPS; **3,143 counties, 0 dropped, 0 errors.**
- Added P2 cut points to `config/thresholds.json`; corrected employment `_count` (101,917 → 65,917).

**Data**: `data/county_scores.json` is now the v2 canonical file; v1 archived to
`data/archive/county_scores_v1_2026-05-17.json`.

**Map** (`labor_organizing_national_dashboard.html`): points at the real data file; the
National/State toggle now **actually recolors the map** (it was a cosmetic no-op); the info card
shows lens-appropriate P1/P2 with the coverage flag; the Tier-1 headline computes live.

**Jobs** (`jobs.html`): fixed the silent MSA data-shape bug + field-name mismatches.

`scoring/sls.py` marked DEPRECATED (dead code, wrong denominator — not used by the real build).

## Verified
- 3 counties hand-checked (LA, Philadelphia, Centre) — reproduce exactly.
- National "clear all three thresholds" = **0** (the expected empirical finding).
- Map served locally with a real fetch: 3,143 counties, **0 JS console errors**, lens toggle
  changes National Tier 1 = 21 / Tier 3 = 59 → State Tier 1 = 141 / Tier 3 = 1,775.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
