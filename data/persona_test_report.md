# Persona Stress Test Report

**Fixes applied since last run:**
  (a) Corrected distance filter: unknown-location jobs kept at bottom, never dropped
  (b) Full lookup chain: firstCity → City,ST → stripped → msa_name → METRO_ALIASES → STATE_CENTERS
  (c) METRO_ALIASES added for Bay Area, NYC Metro, LA, DC, Chicago
  (d) Null fields rendered as '—' not 'n/a'

Persona 1: "Berkeley career-changer"
  Match count: 7 jobs  [previously: 4]
  Delta: +3
  Verdict: PASS  (PASS = 5+ matches)
  Top 3 sample matches:
    1. Internal Organizer UCB @ AFSCME Local 3299 (Berkeley and San Francisco, CA, CA) (0.0mi) - exp_level: 2 - sector: Education
    2. Nursing Practice Representative @ California Nurses Association National Nurses United (Oakland, CA, CA) (4.7mi) - exp_level: 2 - sector: Healthcare
    3. Field Organizer @ CUCFA Council of University of California Faculty Associations (the Bay Area, CA, CA) (10.4mi) - exp_level: 2 - sector: Education
  Notes: Good coverage.

Persona 2: "DC policy researcher"
  Match count: 0 jobs  [previously: 0]
  Delta: 0
  Verdict: FAIL  (PASS = 5+ matches)
  Top 3 sample matches:
    (none)
  Notes: Zero matches — dataset coverage gap for this persona profile.

Persona 3: "Detroit experienced external organizer"
  Match count: 0 jobs  [previously: 0]
  Delta: 0
  Verdict: FAIL  (PASS = 5+ matches)
  Top 3 sample matches:
    (none)
  Notes: Zero matches — dataset coverage gap for this persona profile.

Persona 4: "Houston bilingual healthcare organizer"
  Match count: 0 jobs  [previously: 0]
  Delta: 0
  Verdict: FAIL  (PASS = 5+ matches)
  Top 3 sample matches:
    (none)
  Notes: Zero matches — dataset coverage gap for this persona profile.

Persona 5: "Remote-only legal counsel"
  Match count: 0 jobs  [previously: 0]
  Delta: 0
  Verdict: FAIL  (PASS = 5+ matches)
  Top 3 sample matches:
    (none)
  Notes: Zero matches — dataset coverage gap for this persona profile.

Persona 6: "Chicago comms director"
  Match count: 0 jobs  [previously: 0]
  Delta: 0
  Verdict: FAIL  (PASS = 5+ matches)
  Top 3 sample matches:
    (none)
  Notes: Zero matches — dataset coverage gap for this persona profile.

Persona 7: "Phoenix apprenticeship seeker"
  Match count: 0 jobs  [previously: 0]
  Delta: 0
  Verdict: FAIL  (PASS = 5+ matches)
  Top 3 sample matches:
    (none)
  Notes: Zero matches — dataset coverage gap for this persona profile.

Persona 8: "Atlanta political organizer"
  Match count: 1 jobs  [previously: 1]
  Delta: 0
  Verdict: FAIL  (PASS = 5+ matches)
  Top 3 sample matches:
    1. Lead Organizer @ Workers United-SEIU (Remote, —) - exp_level: 3 - sector: —
  Notes: Only 1 match(es) — marginal dataset coverage.

Persona 9: "Seattle admin/operations"
  Match count: 4 jobs  [previously: 4]
  Delta: 0
  Verdict: FAIL  (PASS = 5+ matches)
  Top 3 sample matches:
    1. Union Representative @ PROTEC17 (Seattle, WA, WA) (0.0mi) - exp_level: 2 - sector: Logistics
    2. Operations Manager @ AFT Washington (Renton, WA, WA) (10.0mi) - exp_level: 4 - sector: Logistics
    3. Executive Assistant to the President @ SEIU Healthcare 1199NW (Seattle, WA, WA) (0.0mi) - exp_level: 4 - sector: Healthcare
  Notes: Only 4 match(es) — marginal dataset coverage.

Persona 10: "NYC nurse rank-and-file"
  Match count: 1 jobs  [previously: 1]
  Delta: 0
  Verdict: FAIL  (PASS = 5+ matches)
  Top 3 sample matches:
    1. Regional Director, New York Private Sector @ SEIU Committee of Interns and Residents (CIR) (New York City, NY Area, NY) (0.0mi) - exp_level: 4 - sector: Healthcare
  Notes: Only 1 match(es) — marginal dataset coverage.

---
## Alias spot-check (3 jobs resolved via METRO_ALIASES)

  location_raw: "New York City, NY"
    alias_key matched: "new york city"
    resolved to: (40.7128, -74.0060)
    distance from NYC NY: 0.0 mi
    employer: American Federation of Musicians of the United States & Canada, AFL-CIO

  location_raw: "New York City, NY"
    alias_key matched: "new york city"
    resolved to: (40.7128, -74.0060)
    distance from NYC NY: 0.0 mi
    employer: Associated Musicians of Greater New York AFM Local 802

  location_raw: "Berkeley and San Francisco, CA"
    alias_key matched: "berkeley and san francisco"
    resolved to: (37.8044, -122.2712)
    distance from Berkeley CA: 4.7 mi
    employer: AFSCME Local 3299

---
## Delta table (vs previous run)

| Persona | Before | After | Delta | Verdict |
|---|---|---|---|---|
| P1 Berkeley career-changer | 4 | 7 | +3 | PASS |
| P2 DC policy researcher | 0 | 0 | 0 | FAIL |
| P3 Detroit experienced external organizer | 0 | 0 | 0 | FAIL |
| P4 Houston bilingual healthcare organizer | 0 | 0 | 0 | FAIL |
| P5 Remote-only legal counsel | 0 | 0 | 0 | FAIL |
| P6 Chicago comms director | 0 | 0 | 0 | FAIL |
| P7 Phoenix apprenticeship seeker | 0 | 0 | 0 | FAIL |
| P8 Atlanta political organizer | 1 | 1 | 0 | FAIL |
| P9 Seattle admin/operations | 4 | 4 | 0 | FAIL |
| P10 NYC nurse rank-and-file | 1 | 1 | 0 | FAIL |

---
PASS: 1 / 10
FAIL: 9 / 10
Most common failure mode: P2 (DC policy researcher): zero matches; P3 (Detroit experienced external organizer): zero matches; P4 (Houston bilingual healthcare organizer): zero matches; P5 (Remote-only legal counsel): zero matches; P6 (Chicago comms director): zero matches; P7 (Phoenix apprenticeship seeker): zero matches; P8 (Atlanta political organizer): only 1 match(es); P9 (Seattle admin/operations): only 4 match(es); P10 (NYC nurse rank-and-file): only 1 match(es)