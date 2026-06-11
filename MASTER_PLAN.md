# TERRAIN — Master Plan v2.0
*The phased build plan. Every session checks this before starting work.*
*Version 2.0 — June 2026*

---

## The Goal

Migrate from the current deployed model (v6, Notion-native scoring) to a peer-review-ready
academic model (v2.0) with a clean four-layer architecture, documented methodology,
and reproducible scoring pipeline.

---

## Phase 0 — Lock the Foundation
*All chat sessions. No code written until Phase 0 is complete.*

| Task | Status | Owner | Output |
|---|---|---|---|
| 0.1 Core assumptions document | ✅ Done | Chat | `TERRAIN_CORE_ASSUMPTIONS.md` |
| 0.2 Model architecture design | ✅ Done | Chat | `MODEL_DESIGN_V2.md` |
| 0.3 Technical specification | ✅ Done | Chat | This document + `SESSION_CONSTITUTION.md` |
| 0.4 Methodology page v2 | ⬜ Next | Chat | `METHODOLOGY_V2.md` + `output/methodology_v2.html` |
| 0.5 Architecture audit | ⬜ Blocked on 0.4 | Code | `AUDIT_CURRENT.md` |
| 0.6 Migration plan | ⬜ Blocked on 0.5 | Chat | `MIGRATION_PLAN.md` |

**Phase 0 is complete when:** Sam has approved `METHODOLOGY_V2.md` and the migration plan.
Nothing in Phase 1+ begins until Phase 0 is fully complete.

---

## Phase 1 — Config Layer
*One Code session. No scoring logic. Just parameters.*

| Task | Status | Dependency | Output |
|---|---|---|---|
| 1.1 Create `config/` directory structure | ⬜ | Phase 0 complete | `config/` skeleton |
| 1.2 Migrate SVS scores to `config/svs_scores.json` | ⬜ | 1.1 | All 42 sector scores, all variables |
| 1.3 Write `config/weights.json` | ⬜ | 1.1 | All formula weights with rationale comments |
| 1.4 Write `config/key_votes.json` | ⬜ | 1.1 | 6-10 defined votes with sources |
| 1.5 Write `config/normalization.json` | ⬜ | 1.1 | Benchmark values for 0-100 scaling |
| 1.6 Write `config/thresholds.json` | ⬜ | 1.1 | Intervention type thresholds (Phase 3 placeholder) |

**Phase 1 is complete when:** All config files exist, Sam has reviewed every value,
and `pytest tests/test_config_integrity.py` passes.

---

## Phase 2 — Ingestion Layer
*Can run as parallel agents once Phase 1 is complete.*
*Each agent owns one script. No agent touches another's script.*

| Task | Status | Agent | Output |
|---|---|---|---|
| 2.1 `ingest_cbp.py` | ⬜ | Agent A | `data/processed/cbp_employment.csv` |
| 2.2 `ingest_qcew_gov.py` | ⬜ | Agent A | `data/processed/qcew_gov_employment.csv` |
| 2.3 `ingest_mit_elections.py` | ⬜ | Agent B | `data/processed/election_margins.csv` |
| 2.4 `ingest_ncsl.py` | ⬜ | Agent B | `data/processed/chamber_seat_counts.csv` |
| 2.5 `ingest_census_crosswalk.py` | ⬜ | Agent B | `data/processed/district_county_crosswalk.csv` |
| 2.6 `ingest_propublica.py` | ⬜ | Agent C | `data/processed/federal_key_votes.csv` |
| 2.7 `ingest_votesmart.py` | ⬜ | Agent C | `data/processed/state_key_votes.csv` |
| 2.8 `ingest_opensecrets.py` | ⬜ | Agent C | `data/processed/federal_campaign_finance.csv` |
| 2.9 `ingest_followthemoney.py` | ⬜ | Agent C | `data/processed/state_campaign_finance.csv` |

**Phase 2 is complete when:** All processed data files exist and pass integrity checks.

---

## Phase 3 — Scoring Layer
*Can run as parallel agents once Phase 2 is complete.*

| Task | Status | Agent | Output |
|---|---|---|---|
| 3.1 `scoring/svs.py` | ⬜ | Agent A | SVS per sector, reads config |
| 3.2 `scoring/sls.py` | ⬜ | Agent A | SLS-Capital, SLS-Community per county |
| 3.3 `scoring/crosswalk.py` | ⬜ | Agent B | District → county averaging |
| 3.4 `scoring/p1_presidential.py` | ⬜ | Agent B | Presidential leverage per county |
| 3.5 `scoring/p1_congressional.py` | ⬜ | Agent B | Congressional leverage per county |
| 3.6 `scoring/p1_state_leg.py` | ⬜ | Agent B | State leg leverage per county |
| 3.7 `scoring/p2_alignment.py` | ⬜ | Agent C | Incumbent alignment per county |
| 3.8 Tests for all scoring functions | ⬜ | Agent D | `tests/` — all scoring tests passing |

**Phase 3 is complete when:** All scoring functions pass unit tests with known inputs/outputs.

---

## Phase 4 — Pipeline and Export
*One Code session. Depends on all of Phase 3.*

| Task | Status | Output |
|---|---|---|
| 4.1 `pipeline/build_county_scores.py` | ⬜ | Orchestration script |
| 4.2 `pipeline/validate.py` | ⬜ | Pre-export integrity checks |
| 4.3 `pipeline/export.py` | ⬜ | `data/county_scores.json` |
| 4.4 Version stamping | ⬜ | Model version + config hash in JSON header |
| 4.5 Full 3,144-county test run | ⬜ | Requires Sam approval before running |

**Phase 4 is complete when:** Pipeline produces a fully valid `county_scores.json`
and Sam has spot-checked scores for 10+ counties against manual calculations.

---

## Phase 5 — Display Layer Migration
*One Code session. Depends on Phase 4.*

| Task | Status | Output |
|---|---|---|
| 5.1 Update map to read `sls_capital` and `sls_community` | ⬜ | Capital/Community lens now data-driven |
| 5.2 Update goal toggle to use new P1 fields | ⬜ | Presidential/Congressional/State leg from data |
| 5.3 Update tooltip to show new field names | ⬜ | All labels match `METHODOLOGY_V2.md` |
| 5.4 Remove orphaned fields from display | ⬜ | `terrain_score` removed from JSON |
| 5.5 Fix NC swing state display bug | ⬜ | NC shown in presidential view |

---

## Phase 6 — Intervention Type (Phase 3 of model)
*Separate work stream. Does not block Phase 1-5.*

| Task | Status | Output |
|---|---|---|
| 6.1 Design intervention type classifier v2 | ⬜ Chat | Decision in `METHODOLOGY_V2.md` |
| 6.2 `ingest_cornell.py` | ⬜ | Strike data pipeline |
| 6.3 `ingest_lm2.py` | ⬜ | Union locals pipeline |
| 6.4 `scoring/intervention.py` | ⬜ | A/B/C classifier |

---

## Parallel Agent Protocol

### Safe to run in parallel:
- Phase 2 agents A, B, C (each owns different data sources)
- Phase 3 agents A, B, C, D (each owns different scoring modules)
- Phase 6 can run alongside Phase 2-3

### Never run in parallel:
- Phase 0 tasks (must be sequential — each builds on the last)
- Phase 1 (one session, must be reviewed as a unit)
- Phase 4 (depends on all of Phase 3)
- Phase 5 (depends on Phase 4)

### Handoff protocol between parallel agents:
1. Agent completes task
2. Sam reviews output
3. Sam updates `STATUS.md` marking task complete
4. Dependent task can begin

---

## Known Risks

| Risk | Mitigation |
|---|---|
| Notion write timeouts | Export to local files first, Notion is secondary |
| Large file reads crashing context | `.claudeignore` + read 10 records max |
| Agents conflicting on shared files | Each agent owns one layer, no crossover |
| Config changes invalidating previous runs | Version stamp every pipeline output |
| Regression validation requiring historical data | Archive data vintages before updating |

---

## Definition of Done

The model is peer-review ready when:
- [ ] `METHODOLOGY_V2.md` documents every decision
- [ ] Every weight and threshold is in `config/` with rationale comments
- [ ] Every scoring function has a docstring citing the theoretical grounding
- [ ] `pytest` passes with >90% coverage
- [ ] A researcher can clone the repo and reproduce all 3,144 county scores
- [ ] Known limitations are documented in `METHODOLOGY_V2.md`
- [ ] The regression validation against 20-30 known campaigns is complete
