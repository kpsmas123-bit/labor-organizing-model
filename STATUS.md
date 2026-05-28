# STATUS.md
_Last updated: 2026-05-28 — classification system session (stoic-agnesi-6d1e4a)_
_Update this file at the end of every session. Commit with the session's git commit._

---

## WHERE WE ARE

**Scoring model:** Pipeline complete through Task 8. Task 9 test run done (200 counties). Full run blocked — see below.

**Jobs board:** 434 jobs (411 unionjobs.com, 22 Arena, 1 AFL-CIO NY). Two-phase classification system fully built. GitHub Actions weekly scraper live. Experience schema upgraded to 4-bucket string system. 86-test regression suite passing. Pending: `impact_score` / `oos_score` enrichment still missing.

---

## 🔴 BLOCKER — Task 9 Full Run

One thing blocking approval:
1. Sector Community-Facing re-audit — all 20 sectors against the corrected 3-part definition
2. Spot-check SVS values after re-audit (Hospitals=100, K-12=100, Ports=75, Retail=10, Manufacturing=25)
3. Reverse case study validation (5 cases)
4. Sam approves → run `scripts/task9_fast.py` (~30 min) → `scripts/export_county_scores.py`

Do not run Task 9 without explicit approval. Every formula change requires a full re-run.

---

## 🟡 NEXT UP (in order)

1. Port `impact_score` / `oos_score` / `is_swing_state` enrichment into `pipeline/classify_jobs_rules.py` (currently sort scores are meaningless — all default to 0/50)
2. NLx response overdue — follow up at nlxresearchhub@naswa.org
3. Sector re-audit → Task 9 approval → full run
4. Consider running monthly API enrichment (`python -m pipeline.enrich_jobs`) to refresh `enriched_jobs.json` ground truth with the new 4-bucket schema

---

## 🟢 RECENTLY SHIPPED — 2026-05-28

### GitHub Actions weekly scraper live
`.github/workflows/scrape_jobs.yml` — runs every Monday at 07:00 UTC. Scrapes unionjobs.com, Arena, and NY AFL-CIO. Runs rules classifier after each ingest. Commits and pushes automatically. Previously listed as "not built" in audit — now live and pushed.

### Two-phase classification system
- **Phase 1 — `pipeline/enrich_jobs.py`** (monthly, manual): calls Claude API (`claude-haiku-4-5-20251001`) on all jobs to produce `data/enriched_jobs.json` as ground truth. Async with `asyncio.Semaphore(10)`, `--resume` flag for incremental runs. 434/434 jobs enriched.
- **Phase 2 — `pipeline/classify_jobs_rules.py`** (weekly, deterministic): reproduces API classifications using keyword rules. Runs in every cron cycle. `--compare` flag reports per-field accuracy against `enriched_jobs.json`. No API cost in the automated pipeline.

### 4-bucket experience schema (replaces integer 1–4)
Old: `exp_level` integer 1–4. New: `experience_level` string + `experience_confidence` float.

| Bucket | Signals | Confidence |
|---|---|---|
| `new-to-labor` | fellowships, internships, apprenticeships, organizer-in-training, "no experience required" | 0.9 (title) / 0.7 (description) |
| `early-career` | junior, Grade-I titles, clerks, administrative/program assistants | 0.9 |
| `experienced` | mid-level organizers, specialists, representatives, coordinators | 0.7 |
| `leadership` | Director of X, VP, Executive Director, Chief, President, General Counsel | 0.9 / 0.7 |

**Classifier accuracy vs Claude API ground truth:** `experience_level` 80.2% ✓ · `job_function` 82.3% ✓ · `location_type` 97.5% ✓ (all fields ≥ 80% target)

**jobs.html updated:** "Early Career" filter pill surfaces both `new-to-labor` and `early-career` jobs; `new-to-labor` pinned to top within results. No separate UI option — single pill, two tiers.

### Systemic classification fixes (5 issues diagnosed and repaired)
1. **Senior ≠ Leadership** — removed bare `\bsenior\b` from `_LEAD_MOD_RE`. "Senior Field Representative" now correctly → `experienced`, not `leadership`.
2. **Speechwriter/creative → communications** — added `speechwriter`, `copywriter`, `creative\s+lead` to `_COMM_KW_RE`. Fixes "Executive Speechwriter" (was `organizing`).
3. **Vague regional locations** — "the Northeast Region (CT, DE, MA…)" had `state='DE'` (scraped from state list). Added `_REGION_SPAN_RE` to null city/state and infer region only.
4. **City sanitization** — "Campaign Washington, DC" → `city='Campaign Washington'`. Added `_sanitize_city()` that strips leading noise words via CITY_REGION_MAP last-word lookup.
5. **Arena employer blank** — 22 Arena jobs had no employer. Fixed in `arena.py` `_parse_html_cards` (future scrapes) and `enrich_job()` (existing records). 17/22 now populated; 5 genuinely have no employer in title.

### 86-test regression suite
`tests/test_classifier.py` — runs in 0.06s. Covers all four classifier functions.
- 10 spot-check ground truth cases (parametrized)
- 5 `senior-without-director-is-not-leadership` edge cases
- 10 new-to-labor title signals + 1 description signal + 1 override test
- 8 communications keyword tests
- 4 location parsed edge cases (Northeast region, Campaign Washington, Remote-to-start, Midwest)
- 12 location type cases

CI: `.github/workflows/tests.yml` — runs `pytest tests/test_classifier.py -v` on every push and PR to `main`.

### Automated monthly API verification
`pipeline/verify_classifications.py` — samples 30 jobs (50% low-confidence, 50% random), re-classifies via `claude-haiku-4-5-20251001` (~$0.01–$0.05/run), compares against rules output. If any field <80% agreement: writes `data/verification_report.json` with per-field stats and targeted rule amendment proposals. Wired into `scrape_jobs.yml` as `workflow_dispatch`-only step.

---

## 🟢 PREVIOUSLY SHIPPED

- **Terrain intro overlay** (5318ffd, May 19) — 9-slide scroll-snap walkthrough on `labor_organizing_national_dashboard.html`.
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
- `data/enriched_jobs.json` — ground truth for classifier; do not overwrite without re-running `--compare`

---

## 📋 AUDIT GAPS — updated status

| Issue | Prior status | Current status |
|---|---|---|
| Weekly cron | Not built | ✅ Live — `.github/workflows/scrape_jobs.yml` |
| Experience filter in jobs.html | Broken (used legacy fields) | ✅ Fixed — uses `experience_level` string + `experience_confidence` |
| Multi-board ingestion | Orphan commit not merged | ✅ Live — Arena + AFL-CIO NY in pipeline |
| Two active classifiers / no migration plan | Open | ✅ Resolved — `classify_jobs_rules.py` is canonical; legacy `classify_jobs.py` kept for `jobs_data.json` only |
| `impact_score` / `oos_score` missing | Active bug | 🔴 Still missing — next priority |
| `scrape_apprenticeships.py` | Paused | 🔴 Still paused — NLx no response |
| `config.json` tracked in git | Open | Not addressed this session |
| `.env.example` missing | Open | Not addressed this session |

---

## ⏰ EXTERNAL PENDING

- **NLx Research Hub** — response was due May 24–31. Overdue. Follow up: [nlxresearchhub@naswa.org](mailto:nlxresearchhub@naswa.org)

## 2026-05-19 — Custom domain configured

- Cloudflare DNS set up for laborterrain.org
  - 4 A records (@ → 185.199.108-111.153), all DNS only / no proxy
  - CNAME (www → kpsmas123-bit.github.io), DNS only
- GitHub Pages custom domain saved, DNS check passed
- CNAME file confirmed on remote (laborterrain.org)
- HTTPS cert provisioning in progress — enforce HTTPS pending
