# Classification Logic — Living Document

_Last updated: 2026-05-30_

> **This document is auto-updated.** Running `python -m pipeline.classify_jobs_rules` refreshes
> the timestamp. Passing `--changelog "message"` appends a changelog entry.

---

## Experience Level

### Schema

| Bucket | Meaning | Confidence values |
|---|---|---|
| `new-to-labor` | Fellowship, internship, apprenticeship, or training program — no prior labor movement experience required by design | 0.9 (title signal), 0.7 (description signal) |
| `early-career` | First real job in the labor movement — organizer, clerk, assistant, Grade-I position, coordinator without seniority | 0.9 / 0.7 |
| `experienced` | Mid-level staff: representative, specialist, manager, senior individual contributor | 0.7 / 0.5 |
| `leadership` | Director, VP, ED, C-suite, President, General Counsel, Supervisor, Business Agent | 0.9 / 0.7 |

Confidence values are stored in `experience_confidence` and control UI blurring at bucket boundaries (see _UI behavior_ below).

### Rules (in order of precedence)

Rules fire top-to-bottom; first match wins.

**1. new-to-labor (0.9) — title keyword**
Pattern: `\b(intern(ship)?s? | fellow(ship)?s? | apprentice(ship)?s? | entry[\s-]level | organizer(s)?[\s-]in[\s-]training | training\s+program | new\s+grad(uate)?s? | recent\s+grad(uate)?s?)\b`

_Why:_ These structured programs are definitionally open to people with no prior union experience. The title is the strongest possible signal — if it says "Fellowship" or "Apprenticeship", classification is certain. Fires before ALL other checks so a "Senior Fellowship" still lands in new-to-labor, not leadership.

**2. new-to-labor (0.7) — description snippet**
Pattern on `title + description[:500]`: `no (prior) experience (is) required | 0 years of experience | new/recent grad(uate)(s)`

_Why:_ Lower confidence (0.7) because descriptions are noisier — a posting describing one part of a multi-role program might use this phrase without the whole role being entry-level.

**3. early-career (0.7) — "Temporary" in title**
_Why:_ Temporary/limited-duration positions in union context are almost always short-term organizer or trial roles. Regardless of other seniority language in the title, temporary = entry posture.

**4. experienced (0.5) — Executive Administrative/Program Assistant, or "Executive Assistant to…"**
_Why:_ These support executives directly; they are not junior admin roles. Without this override they'd fall through to early-career via the "administrative assistant" early-strong pattern.

**5. leadership (0.9) — strong title keywords**
Covers: Executive Director, Vice President, VP, CEO, COO, CFO, Chief [X] Officer, Chief of Staff, "Chief" (excluding "Chief Shop Steward"), "Director of [X]", President (excluding "of the/a"), General Counsel.

_Why:_ These titles are unambiguous in any organizational context, labor movement included.

**6. early-career (0.9) — explicit entry markers in title**
Covers: junior, Specialist/Rep/Analyst/Coordinator/Organizer Grade I, law/record/data/file clerk, Clerk I, receptionist, administrative/office/program assistant, division assistant, field educational assistant, worksite organizer, construction-worker organizer, LIG organizer, UAOU organizer.

_Why:_ These role names explicitly denote entry level, either by grade suffix (Grade I) or by function type (clerk, receptionist, assistant). High confidence (0.9) because title is the most reliable signal.

**7. leadership (0.7) — moderate title keywords**
Covers: lead counsel/researcher/analyst/representative/attorney/coordinator, director (without "of"), supervisor, business agent, deputy director.

_Why:_ "Director" without "of" is still a director — just named differently. Supervisors and Business Agents in union context are senior roles managing member relations or organizing teams.

**8. early-career (0.7) — "Associate" (non-director)**
Pattern: `\bassociate\b` NOT followed by vice/dean/director/general/vp.

_Why:_ "Associate Organizer" or "Associate [Role]" indicates a junior version of a role. Exception carved out for Associate Director, Associate General Counsel, etc. which are leadership/experienced.

**9. early-career (0.7) — API exp_level = 1**
_Why:_ The upstream API assigns exp_level=1 for entry-level positions. Used as a fallback when title patterns don't fire.

**10. experienced (0.5) — API exp_level = 4 without a clear leadership title**
_Why:_ exp_level=4 should be leadership, but without a clear title signal we down-grade confidence to 0.5 to avoid over-classifying ambiguous senior individual contributors.

**11. early-career (0.7) — Coordinator suffix (exp 2 or 3, no scope qualifier)**
_Why:_ "Coordinator" in labor titles usually means a supporting/entry role unless preceded by a scope qualifier (Senior, National, Regional, Lead, UC-campus name, Contracts). With a scope qualifier it becomes experienced.

**12. early-career (0.7) — role_type = Communications, exp = 2, no scope qualifier**
_Why:_ Entry comms staff (digital organizer, press assistant, communications coordinator) are coded Communications by the API with exp=2. Without a scope qualifier indicating senior communications leadership, these are early-career.

**13. early-career (0.7) — role_type = External/Internal organizer, exp = 2, no scope qualifier, no "Representative" in title**
_Why:_ External and internal organizers at exp=2 are front-line staff without scope elevation. "Representative" in title (e.g., "Field Representative") indicates a more experienced role handling member services, not just canvassing.

**14. early-career (0.7) — role_type = Union job, exp = 2, no scope/experienced qualifier**
_Why:_ Union job exp=2 without explicit experienced-level keywords (representative, specialist, negotiator, business agent, labor relations, legislative, advocacy, governance, collective bargaining, secretary, educator, engineer, programmer) defaults to early-career.

**15. experienced (0.7) — exp = 2 or 3, no early-career rule triggered**
**16. experienced (0.5) — fallback (no signal)**

### Scope qualifier list

`national | regional | lead | senior | sr. | uc[campus] | contracts`

When any of these appear in a title alongside a coordinator/organizer/Union job pattern, the early-career rules are suppressed and the role falls through to experienced.

### Key decisions made

| Decision | Reason |
|---|---|
| "Senior X is NOT leadership" | In labor movement context, "Senior Organizer" means experience tier, not a management role. The only seniority-→-leadership bridge is through explicit director/VP/chief titles. |
| "Internal Organizer is NOT new-to-labor" | `\bintern\b` uses word boundaries — "Internal" fails because `intern` is followed immediately by `al` (a word character). More importantly, "Internal Organizer" in union parlance means organizing within existing membership; it's an established role requiring prior labor experience, not a trainee program. |
| "Associate General Counsel is NOT early-career" | The `\bassociate\b` early-career pattern explicitly excludes when followed by general/counsel/director/VP/dean. AGC is an experienced legal role. |
| "Training Director/Specialist is NOT new-to-labor" | The pattern requires `\btraining\s+program\b` — two words in sequence. "Training Director" or "Education & Training Specialist" doesn't match; only literal training-program roles do. |
| "Temporary without a better signal → early-career" | A "Temporary Senior Representative (6-month)" should still surface for early-career searchers, not get buried under experienced. Temporary roles signal opportunity for people breaking in. |

### Known gaps

- **"Senior" blocklist**: `senior` is in the scope qualifier list (blocks coordinator→early-career) but is NOT in the leadership patterns. This means "Senior Director" → leadership (via director pattern), but "Senior Manager" → experienced (correct), and "Senior Field Rep" → experienced (correct). Verify if any Senior X job should be leadership but isn't.
- **exp_level=4 without title signal (confidence 0.5)**: A small number of jobs API-assigned exp=4 land as `experienced` when they should be `leadership`. These tend to be executive support or specialist roles with no director/VP title.
- **Multi-signal conflicts**: A job titled "Associate Director" fires `_LEAD_MOD_RE` (director without "of") before `_EARLY_MOD_RE` (associate) — landing in leadership/0.7. This is the intended behavior but may mis-classify some "Associate Director of Organizing" roles that are genuinely experienced-level.

---

## Job Function

### Functions

`organizing` | `political` | `legal` | `communications` | `research` | `technology` | `finance` | `operations` | `other`

### Rules (priority order — first match wins)

**1. technology** (title + description)
Covers: IT director/manager/specialist/coordinator, web developer, software engineer, database admin, systems administrator, data engineer, cybersecurity, devops, helpdesk, network administrator, data director/infrastructure/analytics.

Checked against title AND description because tech roles often describe technical work in job descriptions even when titles are generic.

**2. finance** (title + description)
Covers: accountant, accounting, bookkeeper, payroll, treasurer, comptroller, budget analyst/director/manager, fiscal, auditor, financial analyst, finance director/manager/associate/coordinator, deputy finance.

**3. political** (title only)
Covers: political, electoral, legislative, lobbyist/lobbying, advocacy, voter access/outreach/registration/protection, GOTV, civic engagement, campaign manager/director/coordinator/organizer, ballot access/initiative, field director (not "field director of organizing"), civil rights, women's rights (not "women's rights organizing"), special programming, ground game, state lead/director (without "union"), regional campaign.

_Why title-only:_ Many union job descriptions mention politics or elections in context without the job being a political role. Checking title-only prevents false positives.

**4. legal** (title only)
Covers: attorney, general/labor counsel, paralegal, legal assistant/director/representative, staff attorney, senior counsel.

**5. communications** (title only)
Covers: communications director/specialist/coordinator/manager, press secretary/director, media director/relations/strategist, messaging, digital director/strategist/organizer, creative director/lead, public relations, graphic designer, content director/manager, social media, marketing director/manager, speechwriter, copywriter.

**6. research** (title only, with political override)
Covers: researcher, research analyst/director/associate/coordinator, policy analyst/director/researcher, polling analyst, data analyst (not "data analyst and infrastructure"), strategic researcher, research and organizer.

_Political override:_ If title matches research AND contains "legislative", classifies as `political` not `research`. "Legislative Policy Analyst" is political work.

**7. organizing** (explicit title keywords)
Covers: organizer, organizing, strategic campaigns director, organizational consultant, field representative/coordinator/staff, labor/union representative, member organizer/outreach, internal/external organizer, organizing director/manager/coordinator.

This step rescues jobs that have obvious organizing titles but were mapped to wrong role_types by the upstream API (e.g., "Admin/operations" for a field coordinator).

**8. role_type mapping fallback**

| API role_type | job_function |
|---|---|
| Internal organizer | organizing |
| External organizer | organizing |
| Union job | organizing |
| Apprenticeship | organizing |
| Communications | communications |
| Political/electoral | political |
| Research | research |
| Legal | legal |
| Admin/operations | operations |
| _(no match)_ | other |

### Key decisions made

| Decision | Reason |
|---|---|
| Technology and finance checked against title+desc | These domains have narrow enough vocabulary that description-level keywords (e.g., "manages Salesforce database") are reliable. |
| Political, legal, comms, research — title only | These terms appear in descriptions of unrelated roles ("we advocate for workers" ≠ an advocacy/political job). |
| Research + "legislative" → political | A researcher working on legislative strategy is fundamentally a political function, not a data/policy research function. |
| `field director` without "of organizing" → political | "Field Director" in campaign context = political role; "Field Director of Organizing" is an organizing leadership role. The negative lookahead distinguishes them. |

### Known gaps

- **Education & training roles**: "Education & Training Specialist" classifies as `other` (no keyword match, role_type = Admin/operations). Should arguably be `operations` or a future `education` function.
- **HR roles**: Human resources jobs often fall through to `operations` or `other`. No explicit HR keyword in the function classifier.
- **Bilingual premium jobs**: Jobs marked bilingual/multilingual are all functions — no special signal.

---

## Location Matching

Location resolution happens in two layers: the **Python classifier** (`classify_location_parsed` in `classify_jobs_rules.py`) enriches the stored JSON at scrape time, and the **JavaScript distance engine** (`lookupJobCentroids`, `isZeroDistanceForUser` in `jobs.html`) runs at query time in the browser.

### Python layer (stored in `location_parsed`)

`classify_location_parsed` produces `{city, state, region, near_airports, raw}` for each job.

**State inference from bare names**
When `state_abbr` is absent and city is null, the raw location string is scanned for a full state name (e.g., "New Jersey", "Statewide in California"). The first matching full name determines `location_parsed.state`. Longer names checked before shorter substrings: "west virginia" precedes "virginia" to prevent "West Virginia" from matching VA.

**Multi-state region detection**
If the raw string contains a broad regional name (Northeast, Midwest, Southeast, Southwest, Northwest, West Coast, East Coast) with no specific city, `location_parsed.state` is set to null and `region` is inferred from the region name. Any state code embedded in the regional list (e.g., "DE" in a "CT, DE, MA…" Northeast listing) is discarded rather than used as the job state.

_Why:_ A job covering the entire Northeast Region should not appear to be a Delaware job just because "DE" appears first in the state list.

**City sanitization**
Garbled city values from the scraper are cleaned:
- Starts with "Remote" → city discarded (remote job; city is noise)
- Leading noise token in multi-word city → strip leading word, try last 2 then last 1 word against known-city map
- Unknown city → kept as-is (better to preserve than drop)

### JavaScript layer (runtime distance engine)

**Multi-city string parsing (`lookupJobCentroids`)**

Location strings that list multiple cities — `"Sacramento or San Francisco Bay Area, CA preferred"`, `"Oakland / San Jose, CA"`, `"City1, City2, or City3, ST"` — are split on `or`, `and`, `/`, `;`, `,`. Each token is tried against `CITY_CENTROIDS` (key format `"city name|ST"`) and `METRO_ALIASES` (lowercased alias → `[lat, lon]`). All resolved coordinates are collected; `distance_miles` is set to the **minimum** across all candidates.

_Why minimum:_ A job that offers roles in either Sacramento (65mi from Berkeley) or the SF Bay Area (10mi from Berkeley) should appear in a 10mi search — the candidate can apply to the closer location.

**State derivation for centroid lookup**
`st = job.state_abbr || location_parsed.state || ''`

Using `location_parsed.state` as a fallback ensures jobs whose `state_abbr` was never set by the scraper (e.g., bare "New Jersey" → `state_abbr=null`, `location_parsed.state='NJ'`) still get a state-center distance rather than being treated as unknown.

**Fallback chain** (first successful result returned):
1. Each city token against `CITY_CENTROIDS`
2. Each city token against `METRO_ALIASES`
3. `"City, ST"` exact parse on raw
4. Full stripped string against `CITY_CENTROIDS` / `METRO_ALIASES`
5. MSA name first token against `CITY_CENTROIDS`
6. State center from `STATE_CENTERS[st]`
7. Full state name scan in raw (when `st` is empty — last resort)

**Zero-distance override (`isZeroDistanceForUser`)**

Jobs that cover a region are detected at query time and assigned `distance_miles = 0` so they appear in any radius search when the user is inside the covered area. Checked before the centroid lookup.

| Pattern | Trigger condition | Rule |
|---|---|---|
| National | "throughout the United States", "nationwide" | Always distance=0 |
| Statewide | "Statewide in X", "Anywhere in X" | distance=0 if job state = user state (or job has no state) |
| Throughout | "throughout [state list]" | distance=0 if job state matches, or user's 2-letter state code appears in raw |
| Airport region | "must live within 100 miles of major airport (CT, DE, …)" | distance=0 if user's state code is in the raw text list |
| Northern California | `\bnorthern ca(lifornia)?\b` in raw | distance=0 if user in CA with lat > 35.8°N |
| Southern California | `\bsouthern ca(lifornia)?\b` | distance=0 if user in CA with lat ≤ 35.8°N |
| Central Valley | `\bcentral valley\b` | distance=0 if user in CA, lat 35°–40.5°N, lng −122.0° to −119.0° |
| Bay Area | `\bbay area\b` | distance=0 if user in CA and within 60mi of SF centroid [37.7749, −122.4194] |
| County | `[Name] County` | Look up county name as city in `CITY_CENTROIDS`; distance=0 if centroid ≤ 30mi from user |

**What gets excluded from radius searches**
Jobs with `distance_miles = null` (truly unknown location — "Remote", "Unknown", no state or city resolved) are **excluded** from radius filter results. They do not appear even as fallback items. This prevents out-of-state jobs with no geocodable location from appearing in local searches.

_Why:_ Before this rule, any job that couldn't be geocoded was appended to every radius search result, causing NJ jobs to appear in Berkeley 5-mile searches.

### Known gaps

- **"Throughout Washington or Montana"**: The raw text spells out state names; the `[A-Z]{2}` code scan only finds abbreviated codes. The scraper records only one state (MT). A WA user does not see this job. Fix would require full-name-to-code lookup in `isZeroDistanceForUser`.
- **County lookup by name** relies on the county having a same-named city in `CITY_CENTROIDS`. Works for Alameda County (Alameda city exists) but fails for Kern County (no "Kern" city; nearest is Bakersfield). 
- **Multi-state county strings**: `"King County, Whatcom County, … (WA/ID)"` has no state coded at all. Individual county lookups fail (no WA state context). A Seattle user will not see this job on a 10mi filter.
- **"New York City Metro Area"**: handled by `METRO_ALIASES["new york city metro area"]`; but "Metro NY" without a state could fail the state filter if user's state is set.

---

## New-to-Labor Signals

### What makes a new-to-labor job

New-to-labor jobs are **structured entry programs** into the labor movement. They are designed for people with no prior union staff experience. The defining characteristic is the program structure (fellowship, apprenticeship, internship, training cohort) rather than the salary or responsibilities.

### Title signals (confidence 0.9)

| Pattern | Examples |
|---|---|
| `intern(ship)(s)` | Organizing Internship, Organizer Internship |
| `fellow(ship)(s)` | Union Organizer Fellowship, Government Affairs Fellow, Organizing Fellow |
| `apprentice(ship)(s)` | Organizing Apprentice, Hospitality Union Organizing Apprenticeship |
| `entry-level` | Entry-Level Organizer |
| `organizer(s)-in-training` | Union Organizer-in-Training, Organizer-in-Training (LA) |
| `training program` | Organizer Training Program |
| `new/recent grad(uate)(s)` | Recent Graduate Organizer |

Word-boundary enforcement (`\b`) is critical — `\bintern\b` will NOT match "Internal" because `intern` is followed by `al` (a word character). This is intentional: "Internal Organizer" is a mid-career union role, not an intern position.

### Description signals (confidence 0.7)

Used when the title has no explicit new-to-labor keyword but the description explicitly states the entry-level nature:
- "no (prior) experience (is) required"
- "0 years of experience"
- "new/recent graduate(s)"

Lower confidence (0.7) because these phrases can appear in non-entry contexts.

### Why "Internal Organizer" is NOT new-to-labor

1. **Regex boundary**: `\bintern\b` requires a non-word character on both sides. In "Internal", `intern` is followed by `a` — a word character — so the boundary fails.
2. **Semantic intent**: "Internal Organizer" or "Internal Organizing" in union context means organizing workers already inside an employer (as opposed to external/new-shop organizing). These roles typically require 2+ years of labor movement experience and familiarity with contract negotiations and member engagement.
3. **Classification evidence**: All "Internal Organizer" variants in the dataset are classified `early-career` or `experienced` — not `new-to-labor`. This has been verified against the full 434-job corpus.

### UI behavior (Early Career filter in `jobs.html`)

The "Early Career" filter pill in the UI displays **both** `new-to-labor` and `early-career` classified jobs:

```js
if (state.exp === 'early-career')
  return lvl === 'new-to-labor'
      || (lvl === 'early-career' && conf >= 0.7)
      || (lvl === 'experienced' && conf <= 0.5);  // blurred boundary
```

Within the Early Career results, `new-to-labor` jobs are **pinned to the top** via a two-tier sort:
```js
const ntlTier = j => j.experience_level === 'new-to-labor' ? 0 : 1;
filtered.sort((a, b) => ntlTier(a) - ntlTier(b) || (b.impact_score || 0) - (a.impact_score || 0));
```
Tier 0 (new-to-labor) always appears above tier 1 (early-career). Within each tier, sorted by `impact_score` descending.

The UI badge for both `new-to-labor` and `early-career` reads "Early Career" — the distinction is internal to the classifier and is not surfaced to users.

---

## Changelog

| Date | Change |
|---|---|
| 2026-05-29 | Initial document — reverse-engineered from classify_jobs_rules.py, jobs.html, enriched_jobs.json |
| 2026-05-29 | Added statewide containment logic for regional job matching |

---

## Verification

### Run classifier tests (86 unit tests)
```bash
pytest tests/test_classifier.py
```

### Check accuracy against enriched_jobs.json ground truth
```bash
python -m pipeline.classify_jobs_rules --compare data/enriched_jobs.json
```
Target: all three fields (experience_level, job_function, location_type) ≥ 80%.

`new-to-labor` is normalized to `early-career` when comparing against the ground truth (which predates the new-to-labor bucket).

### Run API spot-check
```bash
python -m pipeline.verify_classifications
```

### Update this document after a rule change
```bash
python -m pipeline.classify_jobs_rules --changelog "Added statewide containment logic for regional job matching"
```
This updates the "Last updated" timestamp and appends a changelog row.
