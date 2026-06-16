# State-lens rebuild: competitiveness P1 + party-proxy P2 + recalibrated tiers

**Branch:** `state-lens-rebuild` · **Do NOT merge until you approve the new tier distribution.**
**State lens stays HIDDEN** (Agent 3's gating untouched).

## ⚠️ NEEDS SAM (review before un-gating)
1. **`p1_high_state = 30.0`** — the selectivity knob. Yields **289 counties (9.2%) high-P1** vs ~56% under the
   broken P1 (national high-P1 ≈ 3%). It's a *different scale* from national P1 by design. All tier counts move
   with this number.
2. **BAND = 8.0pp** competitive width (widened from ~3% for gradation). Tunable.
3. **`organized_scale_score` removed in v2** → jobs.html MSA `infraScale` tiebreaker degraded to 0 (Phase 1).
4. **DC + DE (4 counties)** — no chamber data → `p1_state = 0`; DC P2 → 0.5 neutral (`party_proxy_unavailable`).
5. **194 counties** with no district-overlap party → state-uniform Dem-share fallback (`party_proxy_state_uniform`).

## New state-lens tier distribution
| Tier | Was (broken) | Now |
|---|---|---|
| Tier 1 (Transform) | 141 (cap 98 / comm 41 / both 2) | **42** (cap 33 / comm 8 / both 1) |
| Tier 2 (Build/Activate/Unknown) | 446 | **545** (build 461 / activate 60 / unknown 24) |
| Tier 3 (Electoral) | 1,775 | **163** |
| Tier 4 (Neither) | 781 | **2,393** |
| high-P1 share | ~56% | **9.2% (289)** |

## What changed
- **P1_state** = `100 × chamber_flip_proximity × max(0,(8−|margin|)/8)` — bounded, no `1/margin`; chamber-flip
  proximity from `chamber_seat_counts` tipping weights matched to the most-competitive seat's chamber.
- **P2_state** = overlap-weighted Dem share of the **current** state-leg roster (`county_seat_detail.json`),
  0–1 scale; `state_p2_coverage = party_proxy`.
- **Classifier** = existing 6-tier `classify()` per lens (state-specific p1 threshold). New additive
  `state_noncomp_priority` (hostile/neutral/aligned) on the low-P1 band only — preserves the medium/low split.
- New fields: `p1_state_data_tier`, `margin_stale`, `state_noncomp_priority`.
- **National lens + SLS untouched** — verified 0 field diffs across all 3,143 counties.
- County reconcile: 3,143 canonical all scored; non-canonical FIPS 15005 logged, not force-fit.
- Overlay auto-applies `state_leg_competitiveness_backfill.csv` if Agent 5 later merges it (not present now).

Spot-checks + full rationale: `STATE_LENS_REBUILD_PROGRESS.md`. Build: `pipeline/rebuild_state_lens.py --write`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
