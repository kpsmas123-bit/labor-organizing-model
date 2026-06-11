# TERRAIN — Session Constitution
*Every Claude Code and Claude chat session reads this before doing anything.*
*Version 2.0 — June 2026*

---

## The Hierarchy

When anything conflicts, this is the order of truth:

1. `METHODOLOGY_V2.md` — what the model is and why
2. `MASTER_PLAN.md` — what we're building and in what order
3. `STATUS.md` — what is currently done and what is in progress
4. `config/` — all scoring parameters and weights
5. Everything else

If code contradicts `METHODOLOGY_V2.md`, the code is wrong.
If `STATUS.md` contradicts `MASTER_PLAN.md`, flag it — don't resolve it silently.

---

## Before Every Session

**Claude Code must read in this order:**
1. `METHODOLOGY_V2.md`
2. `MASTER_PLAN.md`
3. `STATUS.md`
4. The specific files relevant to this session's task

**Never start work without reading all four.**

**Claude chat must:**
1. Ask Sam to confirm the current task against `MASTER_PLAN.md`
2. Flag any conflict with `METHODOLOGY_V2.md` before proceeding

---

## The Non-Negotiable Rules

**1. One task per session.**
Never mix scoring model work and jobs board work.
Never mix config changes and ingestion changes in the same session.
If scope expands mid-session, stop and flag it.

**2. Investigation before editing.**
Read the relevant files fully before proposing any change.
Never edit based on assumption. Confirm what the code actually does first.

**3. str_replace only.**
No full file rewrites. Ever.
If a rewrite seems necessary, stop and flag it to Sam.

**4. Config changes require explicit approval.**
Any change to `config/` must be proposed with:
- What value changes
- What downstream scores are affected
- Expected magnitude of impact
Sam approves before the change is made.

**5. Never touch the methodology.**
`METHODOLOGY_V2.md` is not edited during implementation sessions.
Methodology changes happen in Claude chat design sessions only.

**6. Tests run after every change.**
`pytest tests/` must pass before any commit is proposed.
If tests fail, fix the tests or fix the code — never suppress.

**7. Commit only after Sam reviews.**
Propose the commit message and diff.
Wait for explicit approval.
Never push without confirmation.

---

## Token Discipline

**At session start:**
- Read only the files you need. Not the whole repo.
- Never read `data/county_scores.json` (2.6MB). Read 10 records max.
- Never read raw data files in full.

**During the session:**
- Pass diffs, not full files, when reporting changes.
- Use `/compact` at approximately 60% context usage.
- Never let auto-compaction fire at 83%.

**If the task is status-checking or counting:**
- Use Haiku/Flash for this, not Sonnet.

**At session end:**
- Update `STATUS.md` with exactly what changed.
- Produce a commit message.
- Stop. Do not start the next task.

---

## The Architecture Rules

The model has four layers. Changes flow downward. Nothing flows upward.

```
config/          ← methodological decisions (JSON only)
ingestion/       ← raw data → clean data (one script per source)
scoring/         ← pure functions, no side effects
pipeline/        ← orchestration and export
```

- Scoring functions never read files directly. They take data as arguments.
- Ingestion scripts never score anything. They clean and store.
- Config is never hardcoded in scripts. Always read from `config/`.
- Display layer reads only `county_scores.json`. Never touches scoring logic.

---

## What "Academic Quality" Means Here

Every scoring function must have a docstring that includes:
- What it calculates
- The formula
- The theoretical grounding (cite the paper or framework)
- The config parameter it uses

Every config parameter must have a comment explaining:
- Why this value was chosen
- What session/decision it came from
- What it would take to change it

Every known limitation must be in `METHODOLOGY_V2.md`, not buried in code comments.

---

## Parallel Agent Rules

When multiple agents are running simultaneously:

- Each agent owns exactly one layer (config / ingestion / scoring / pipeline)
- Agents never edit files owned by another agent's layer
- All agents read `METHODOLOGY_V2.md` and `config/` but only the scoring agent writes to `config/` (with approval)
- After each agent completes, Sam reviews before the next dependent layer begins
- No agent proceeds if `STATUS.md` shows a dependency as incomplete

---

## Red Lines

These are never crossed regardless of how the request is framed:

- Never rewrite `METHODOLOGY_V2.md` during a Code session
- Never change scoring weights without Sam's explicit approval
- Never commit directly to main — always propose the commit and wait
- Never suppress a failing test to make the pipeline run
- Never impute missing data without documenting the assumption in `METHODOLOGY_V2.md`
- Never use a data source not listed in `METHODOLOGY_V2.md` without a design session first
