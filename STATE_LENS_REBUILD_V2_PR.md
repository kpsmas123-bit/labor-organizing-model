# State-Lens Rebuild v2 — plateau-fade competitiveness (GATED, do not merge)

Branch: `state-lens-rebuild-v2` (from updated `main`, post `state-returns-backfill` merge).
**State lens stays HIDDEN. Do NOT merge until Sam picks B.** This SUPERSEDES the
earlier `state-lens-rebuild` dress rehearsal (pre-backfill data + non-final linear band).

---

## ⬇ DECISION B — pick `p1_high_state` from these real numbers

After computing P1_state for all 3,143 counties (412 with nonzero P1):

| `p1_high_state` | high-P1 counties | % of map | Tier 1 | Tier 3 |
|---:|---:|---:|---:|---:|
| **30** | 356 | 11.3% | 50 | 212 |
| **60** | 252 |  8.0% | 36 | 144 |
| **90** |  73 |  2.3% | 12 |  40 |

**Why not {20, 30, 40} as briefed:** on the finalized plateau-fade those three sit on
a flat shoulder — 11.8% / 11.3% / 10.4% of map, all within 1.4pp — so they don't
bracket a real decision. Widened to **{30, 60, 90}** to span from a loose state lens
(~11%) to national-tight (~2%, national high-P1 is ~3%), where Tier 1 / Tier 3 actually
move. Full curve for context:

| `>= P1` | counties | % of map |
|---:|---:|---:|
| 5  | 395 | 12.6% |
| 10 | 391 | 12.4% |
| 20 | 371 | 11.8% |
| 30 | 356 | 11.3% |
| 40 | 327 | 10.4% |
| 50 | 285 |  9.1% |
| 60 | 252 |  8.0% |
| 70 | 211 |  6.7% |
| 80 | 143 |  4.5% |
| 90 |  73 |  2.3% |

`p1_high_state` is currently left at **30.0** in `config/thresholds.json`. Tell me the
number you want and I'll set it in config and finalize. (This is the only selectivity
knob; every tier count above moves with it.)

State tier counts at the current `p1_high_state = 30`:
Tier 1 = 50 (cap 39 / comm 10 / both 1) · Tier 2 = 537 (build 443 / activate 68 /
unknown 26) · Tier 3 = 212 · Tier 4 = 2,344.
Low-P1 alignment subdivision: hostile 2,375 · neutral 142 · aligned 270.

---

## What changed vs the dress rehearsal

1. **Competitiveness → plateau fade** (replaces linear-from-0). `comp(|margin|)`, margin
   in two-party percentage points:
   - `|margin| ≤ PLATEAU_EDGE (3.0)` → **1.0** (toss-up zone, full weight)
   - `PLATEAU_EDGE < |margin| < ZERO_EDGE (8.0)` → `(ZERO_EDGE − |margin|)/(ZERO_EDGE − PLATEAU_EDGE)`
   - `|margin| ≥ ZERO_EDGE (8.0)` → **0.0**

   Continuity verified at the edge: both pieces evaluate to **1.0** at `|margin| = 3.0`.
   `P1_state = 100 × chamber_flip_proximity × comp(margin)`, range 0..~98.

2. **Single-source config.** New `state_competitiveness` block in
   `config/thresholds.json` holds `plateau_edge`, `zero_edge`, `p1_high_state`.
   `pipeline/rebuild_state_lens.py` reads all three from config — **nothing in the
   script hardcodes them** (verified). The candidate/curve thresholds in the report are
   display-only and don't touch scoring.

3. **Overlay auto-applied.** The now-merged
   `data/processed/state_leg_competitiveness_backfill.csv` (393 rows: VA/NJ/MS/LA/NE) is
   picked up — overlay rows replace base rows by FIPS. Confirmed in the log:
   `overlay_found: true`, states `[LA, MS, NE, NJ, VA]`.

4. **VA vintage carried through, no synthetic adjustment.** VA's 133 localities are
   2021-vintage gubernatorial; their staleness is flagged in `p1_state_data_tier`
   (`gubernatorial:2021`). Vintage is carried for **every** row (e.g. base rows read
   `district_actual:2022`). **No swing buffer or synthetic margin adjustment is applied
   to VA or any state** — real margins only. (Most VA/MS/LA/NE localities are deep-margin
   → P1 floors to 0; NJ 2025 is genuinely competitive and scores nonzero.)

5. **National lens + SLS untouched.** Verified **0 field diffs across all 3,143
   counties** (script aborts the write if any national/SLS field changes). Agent 3's
   gating is untouched — the toggle stays hidden, lens forced to national.

6. **Reconciliation (3,143 vs 3,144).** Canonical `county_scores.json` (3,143) is ground
   truth. The one extra competitiveness/seat-detail row — **FIPS 15005 (Kalawao, HI)** —
   is logged, not force-fit. Zero canonical counties missing competitiveness data.

Unchanged from the rehearsal: P2_state (overlap-weighted Dem share of current state-leg
roster), the reused `classify()` 6-tier classifier, the `state_noncomp_priority`
hostile/neutral/aligned subdivision of the low-P1 band, DC+DE P1 floor (no chamber data,
4 counties), 194 state-uniform P2 fallbacks, DC P2 unavailable (neutral 0.5).

---

## Audit record (citable methodological choices)

- "Competitiveness weighted full through ±3% two-party margin (toss-up), linear decay to
  zero at ±8% (lean edge); plateau adopted so the model does not draw distinctions finer
  than the data's reliability (vintage/proxy error)."
- "Stale sources (VA 2021 gubernatorial) included and flagged by vintage; no synthetic
  swing adjustment applied to any state."
- Basis for the ±3 full / ±8 zero band edges: **538's Atlas of Redistricting** treats
  **D+5 / R+5** as the competitive boundary, and **Ballotpedia** classifies a **5–10%**
  margin as "mildly competitive." The ±3 plateau sits inside the toss-up core; the ±8
  zero edge sits at the outer lean boundary those two sources bracket.

---

## Files

- `config/thresholds.json` — new `state_competitiveness` block (plateau_edge 3.0,
  zero_edge 8.0, p1_high_state 30.0).
- `pipeline/rebuild_state_lens.py` — plateau-fade comp, config-sourced params, vintage
  carry-through, 3-threshold selectivity report + full curve, all-county 0-diff guard.
- `data/county_scores.json` — state-lens fields only (p1_state, p2_state,
  quadrant_state, state_p2_coverage, p1_state_data_tier, margin_stale,
  state_noncomp_priority) + `_tier_counts_state` / `_state_lens_rebuild` metadata.
- `data/work_stateleg/state_lens_rebuild_log.json` — overlay, reconciliation,
  selectivity report, full curve, fallbacks, 0-diff confirmation.
- `data/archive/county_scores_pre_state_lens_rebuild.json` — pre-rebuild backup.

Run: `python pipeline/rebuild_state_lens.py` (dry-run report) / `--write` (persist).
