# STATUS.md
_Last updated: 2026-05-19 — intro overlay session (suspicious-heyrovsky-e12991)_
_Update this file at the end of every session. Commit with the session's git commit._

---

## WHERE WE ARE

**Scoring model:** Pipeline complete through Task 8. Task 9 test run done (200 counties). Full run blocked — see below.

**Jobs board:** Phase 1 live. 398 jobs (unionjobs.com only). Pipeline migrated to new `pipeline/` module but schema gap vs. frontend is causing silent feature degradation — see gaps below.

---

## 🔴 BLOCKER — Task 9 Full Run

One thing blocking approval:
1. Sector Community-Facing re-audit — all 20 sectors against the corrected 3-part definition
2. Spot-check SVS values after re-audit (Hospitals=100, K-12=100, Ports=75, Retail=10, Manufacturing=25)
3. Reverse case study validation (5 cases)
4. Sam approves → run `scripts/task9_fast.py` (~30 min) → `scripts/export_county_scores.py`

Do not run Task 9 without explicit approval. Every formula change requires a full re-run.

---

## 🔴 JOBS BOARD — Active Bugs (silent, need fixing)

**1. Experience filter broken**
`jobs.html` lines 1968–1970 filter on `seniority_level`/`is_entry_level` (legacy fields).
`classified_jobs.json` uses `exp_level` (int 1–4). Filter silently fails — buttons do nothing.
Fix: update filter logic in jobs.html to use `exp_level`.

**2. impact_score / oos_score / is_swing_state missing from classified_jobs.json**
New pipeline (`pipeline/classify_jobs.py`) doesn't compute these fields. Legacy pipeline (`scripts/classify_jobs.py`) does.
Result: sort by impact is meaningless (all default to 0/50), swing state badges never show.
Fix needed: decide whether to port enrichment logic to new pipeline or keep legacy pipeline for jobs_data.json.

**3. Orphan commit 9eaf194 not merged**
20 Arena + 1 AFL-CIO NY jobs added in that commit are NOT in current `classified_jobs.json`.
Current board: 398 jobs, all unionjobs.com. No Arena/AFL-CIO/Lockshin jobs.

**4. Persona test: 1/10 pass**
Root cause: single source (unionjobs.com), missing enrichment fields, orphan commit not merged.

---

## 🟡 NEXT UP (in order)

1. Fix experience filter bug in jobs.html (investigation-first)
2. Decide: port impact_score enrichment to new pipeline OR keep legacy pipeline active
3. Merge orphan commit 9eaf194 OR re-run multi-board ingestion
4. Sector re-audit → Task 9 approval → full run
5. Build GitHub Actions weekly cron (`.github/workflows/scrape_jobs.yml`)
6. NLx response due ~May 24–31 → follow up if no reply

---

## 🟢 RECENTLY SHIPPED

- **Terrain intro overlay** (5318ffd, May 19) — 9-slide scroll-snap walkthrough on `labor_organizing_national_dashboard.html`. Replaces orphaned `#onboarding-overlay` CSS. Includes: all 9 slides with final copy, slides 5–6 dim + pulse animation targeting `#lens-badge` / `#lens-btns`, skip button (3s delay), slide progress counter, localStorage `terrain_intro_seen` gate, "Start exploring →" and "Explore case studies ↓" CTAs, horizontally scrollable 8-county case study panel with real scores from `county_scores.json` (Kanawha 40.6, Logan 19.21, Clark 86.5, Cook 86.5, Allegheny 86.5, Maricopa 75.25, Philadelphia 86.5, Multnomah 70.31).
- Map UI v6: lens toggle, goal alignment, intervention type overlay (13b6211, May 19)
- Task 4 v6 CBP employment pipeline (cae6303, May 17)
- Task 9 v6 parallelised scorer — 3,144 counties, A=407/B=1021/C=1716 (test run)
- New `pipeline/` module: ingest, normalize, classify, reclassify, admin server
- City autocomplete: `output/city_centroids.json` (311 KB, 5,000 cities)
- Terrain design system: `output/terrain.css`
- Landing page: `index.html`

---

## ⛔ DO NOT TOUCH

- Full Task 9 run — requires sector re-audit + explicit approval
- `scrape_apprenticeships.py` — paused until NLx responds
- Congressional map view — grayed out, redistricting
- `data/county_scores.json` — do not overwrite without Task 9 approval

---

## 📋 GAPS FOUND IN AUDIT (reconciled against Decisions Log)

### Drift: Decisions Log says, repo disagrees

| Issue | Decisions Log says | Repo state |
|---|---|---|
| `output/jobs_data.json` canonical | Legacy pipeline output, should be live | `classified_jobs.json` loads first — jobs.html prefers it |
| Jobs board schema | `impact_score`, `oos_score`, `is_swing_state` required fields | Not present in `classified_jobs.json` |
| Weekly cron | Spec'd in Phase 1 | Not built — no `.github/workflows/scrape_jobs.yml` |
| `scrape_apprenticeships.py` | Spec'd in Phase 1 | Not built |
| Multi-board ingestion | Arena + AFL-CIO NY live | Orphan commit — not in current branch |
| `config.json` | Should be gitignored | Tracked in git (needs `git rm --cached`) |
| `.env.example` | Implied by security decisions | Does not exist |
| RUN_ORDER.md | Should reflect current pipeline | References `scripts/` only, not `pipeline/` module |

### New issues found in audit (not in Decisions Log)

- `data/raw_jobs.json` missing — pipeline module expects it, file doesn't exist
- Two active classifiers with divergent schemas and no migration plan
- `scripts/_deprecated_fix_sectors.py.bak` tracked in git — should be deleted
- `data/sectors_schema_pre_v6_2026-05-12.json` — stale backup, no longer consumed
- `data/county_scores_test.json` — stale 200-county subset, should be archived

---

## ⏰ EXTERNAL PENDING

- **~May 24–31:** NLx Research Hub response → [nlxresearchhub@naswa.org](mailto:nlxresearchhub@naswa.org)
  If no reply by May 31: follow up directly.

## 2026-05-19 — Custom domain configured

- Cloudflare DNS set up for laborterrain.org
  - 4 A records (@ → 185.199.108-111.153), all DNS only / no proxy
  - CNAME (www → kpsmas123-bit.github.io), DNS only
- GitHub Pages custom domain saved, DNS check passed
- CNAME file confirmed on remote (laborterrain.org)
- HTTPS cert provisioning in progress — enforce HTTPS pending
