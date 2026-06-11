# TERRAIN — Architecture Audit Prompt
# Paste this into a fresh Claude Code session.
# Read-only. No edits. Report only.

---

You are auditing the current Terrain codebase against a target architecture.
This is a read-only investigation session. Do not edit anything. Produce a report.

---

## STEP 1 — Read These First

Read in this order before doing anything else:

```
STATUS.md
CLAUDE.md
```

Then read the target architecture document I am pasting below.
Understand it fully before proceeding.

---

## TARGET ARCHITECTURE (v2.0)

The target system has four layers:

```
config/          ← all scoring parameters as JSON (no hardcoded values in scripts)
ingestion/       ← one script per data source, raw → clean
scoring/         ← pure functions, no file I/O, no side effects
pipeline/        ← orchestration and export only
```

**Config files needed:**
- `config/svs_scores.json` — all 42 sector scores, all variables
- `config/weights.json` — all formula weights
- `config/key_votes.json` — defined key vote list
- `config/normalization.json` — benchmark values for 0-100 scaling
- `config/thresholds.json` — intervention type thresholds

**Scoring functions must:**
- Take data as arguments, not read files directly
- Have docstrings citing theoretical grounding
- Be independently testable

**New scores required:**
- `sls_capital` = Σ(cap_reach_score × raw_employment_in_sector) — normalized
- `sls_community` = Σ(comm_reach_score × employment_share_in_sector) — normalized
- `p1_presidential` = state_tipping_weight × (1 / abs(margin_presidential))
- `p1_congressional` = district margin averaged to county via Census crosswalk
- `p1_state_leg` = chamber_tipping_weight × district_margin, averaged to county
- `p2_alignment` = key_vote_score × 0.60 + inverse_business_funding × 0.40

---

## STEP 2 — File Inventory

List every file in:
```
scripts/
pipeline/
scoring/ (if exists)
config/ (if exists)
data/ (filenames and sizes only)
output/ (filenames only)
tests/
```

Note which directories from the target architecture exist vs. do not exist yet.

---

## STEP 3 — Hardcoded Values Audit

Search every script in `scripts/` and `pipeline/` for:
- Numeric literals used in formulas (weights, thresholds, caps, floors)
- Any value that belongs in `config/` but lives in code

For each: file, line number, value, what it does, whether it has a comment.

---

## STEP 4 — Current Scores vs. Target Scores

For each target score listed above, answer:
- Does it currently exist in the codebase? Under what name?
- Is the formula the same or different from the target?
- What would need to change to match the target?

Also document:
- Which current scores exist that have NO equivalent in the target architecture
- Which current fields in `county_scores.json` are never displayed anywhere

---

## STEP 5 — Data Flow Audit

Trace the current data flow from raw data to `county_scores.json`:
- What scripts run in what order?
- Is that order enforced anywhere or just conventional?
- What would break if scripts ran out of order?
- Are there any circular dependencies?

---

## STEP 6 — Config Layer Gap

Does `config/` exist? If not:
- List every hardcoded value across all scoring scripts
- Group them by: SVS scores / formula weights / thresholds / normalization benchmarks
- This becomes the config migration list

---

## STEP 7 — Test Coverage

List every file in `tests/`.
For each scoring function in the current codebase:
- Is it tested?
- Does the test check a known input/output pair or just that it runs without error?

---

## STEP 8 — Migration Risk Assessment

For each component of the target architecture, assess:
- How much current code is reusable vs. needs rewriting?
- What data would be lost or changed during migration?
- What is the risk of breaking the current live map during migration?

---

## STEP 9 — Report

Print the following. Be specific. No summaries that lose detail.

```
# TERRAIN ARCHITECTURE AUDIT
Generated: [date]

## 1. File Inventory
[complete list with notes on what exists vs. target]

## 2. Hardcoded Values
[every numeric literal by file and line]

## 3. Current vs. Target Scores
[field by field comparison]

## 4. Data Flow
[current pipeline order, enforcement, risks]

## 5. Config Layer Gap
[all values that need to move to config/]

## 6. Test Coverage
[current state, gaps]

## 7. Migration Risk
[component by component]

## 8. What Can Run in Parallel
[which migration tasks are independent vs. dependent]

## 9. Estimated Effort
[rough estimate per phase: hours / days]
```

Do not propose fixes. Do not edit any file. Print the report and stop.
