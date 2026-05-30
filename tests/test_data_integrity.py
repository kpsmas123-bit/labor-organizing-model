"""
Data integrity tests for unionjobs.com scraper output.

Tests are run against output/unionjobs_raw.json — the canonical scraper output
(after --reparse has been applied to clean legacy records).

These tests verify:
  1. No job description contains raw structured-field labels (Location:, Department:).
  2. Jobs whose Compensation: field was populated have parseable salary data.
  3. Description content is substantive (no very-short stub strings).
"""
import json
from pathlib import Path

import pytest

RAW_OUTPUT = Path("output/unionjobs_raw.json")


def _load_raw():
    if not RAW_OUTPUT.exists():
        pytest.skip(f"{RAW_OUTPUT} not found — run scripts/scrape_unionjobs.py first")
    with open(RAW_OUTPUT, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 1. No structured field labels in description
# ---------------------------------------------------------------------------

def test_no_structured_labels_in_description():
    """No job description should contain raw structured field labels.

    Labels such as 'Location:' and 'Department:' belong in dedicated fields,
    not inside the prose description.  The scraper (and --reparse) strips them.
    """
    jobs = _load_raw()
    contaminated = [
        j["job_id"]
        for j in jobs
        if any(lbl in (j.get("description") or "") for lbl in ("Location:", "Department:"))
    ]
    assert contaminated == [], (
        f"{len(contaminated)} job(s) have structured labels in description: "
        f"{contaminated[:10]}"
    )


# ---------------------------------------------------------------------------
# 2. Compensation: label → salary parseable
# ---------------------------------------------------------------------------

def test_compensation_label_implies_parseable_salary():
    """Jobs whose salary_raw has 'Compensation:' AND a dollar amount should parse salary_min > 0.

    When the scraper extracts a Compensation: field from the structured block and that field
    contains a numeric dollar value, the normalize pipeline (parse_salary) must resolve a
    positive salary_min.  Records with 'Compensation:' but no dollar sign (rare edge cases
    where the org described the compensation in words only) are excluded.
    """
    import re
    from pipeline.parsers.salary import parse_salary

    jobs = _load_raw()
    failures = []
    for j in jobs:
        sal_raw = j.get("salary_raw") or ""
        if not sal_raw.startswith("Compensation:"):
            continue
        # Only check records where the dollar amount follows directly after Compensation:
        # (possibly with a sub-label like "Salary Range:" or "Hourly Rate:").
        # Records with long prose before the dollar are excluded because parse_salary
        # may pick up contextual numbers (dates, step grades) as salary amounts.
        if not re.match(
            r'Compensation:\s*(?:(?:Salary Range|Hourly Rate|Annual Salary)\s*:\s*)?\$[\d]',
            sal_raw,
            re.IGNORECASE,
        ):
            continue
        parsed = parse_salary(sal_raw)
        sal_min = parsed.get("salary_min")
        if not sal_min or sal_min <= 0:
            failures.append((j["job_id"], sal_raw[:80]))

    assert failures == [], (
        f"{len(failures)} jobs have 'Compensation: $...' in salary_raw but salary_min <= 0: "
        f"{failures[:5]}"
    )


# ---------------------------------------------------------------------------
# 3. Descriptions are substantive — no very-short stub strings
# ---------------------------------------------------------------------------

def test_description_no_stub_strings():
    """Non-empty descriptions should be substantive (> 50 chars).

    Very short descriptions (1–50 chars) indicate truncation artifacts or
    parser errors that left only a fragment of text.
    """
    jobs = _load_raw()
    stub_jobs = [
        (j["job_id"], j["description"])
        for j in jobs
        if j.get("description") and 0 < len(j["description"]) < 50
    ]
    assert stub_jobs == [], (
        f"{len(stub_jobs)} job(s) have suspiciously short descriptions: {stub_jobs}"
    )


# ---------------------------------------------------------------------------
# 4. Structured-block fields extracted correctly for SEIU-style listings
# ---------------------------------------------------------------------------

def test_seiu_structured_fields_populated():
    """Records with the SEIU structured-block format should have department set.

    These listings contain 'Location: X Department: Y Employment Type: Z
    Minimum Experience: W Compensation: $' as a block — the scraper extracts
    each field into a dedicated key.
    """
    jobs = _load_raw()
    # Records with experience_raw set must also have department set
    exp_without_dept = [
        j["job_id"]
        for j in jobs
        if j.get("experience_raw") and not j.get("department")
    ]
    assert exp_without_dept == [], (
        f"Jobs with experience_raw but no department: {exp_without_dept}"
    )


# ---------------------------------------------------------------------------
# 5. salary_raw field present (renamed from legacy 'salary')
# ---------------------------------------------------------------------------

def test_no_legacy_salary_key():
    """The scraper outputs 'salary_raw', not the legacy 'salary' key.

    After --reparse all records should use the canonical field name.
    """
    jobs = _load_raw()
    legacy = [j["job_id"] for j in jobs if "salary" in j and "salary_raw" not in j]
    assert legacy == [], (
        f"{len(legacy)} records still use the legacy 'salary' key: {legacy[:5]}"
    )


# ---------------------------------------------------------------------------
# Intelligence card field rules — tested against classified_jobs.json
# ---------------------------------------------------------------------------

CLASSIFIED_PATH = Path("data/classified_jobs.json")


def _load_classified():
    if not CLASSIFIED_PATH.exists():
        pytest.skip(f"{CLASSIFIED_PATH} not found — run pipeline.classify_jobs_rules first")
    with open(CLASSIFIED_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_seiu_employer_union_affiliation():
    """Jobs with 'SEIU' in employer should have union_affiliation = 'SEIU'."""
    jobs = _load_classified()
    seiu_jobs = [j for j in jobs if "SEIU" in (j.get("employer") or "")]
    assert seiu_jobs, "No SEIU jobs found — check data"
    wrong = [j["job_id"] for j in seiu_jobs if j.get("union_affiliation") != "SEIU"]
    assert wrong == [], f"SEIU jobs with wrong union_affiliation: {wrong[:5]}"


def test_attorney_title_professional_staff():
    """Jobs with 'attorney' in title should have professional_staff = 'professional'."""
    jobs = _load_classified()
    import re
    attorney_jobs = [j for j in jobs if re.search(r'\battorney\b', j.get("title") or "", re.IGNORECASE)]
    assert attorney_jobs, "No attorney jobs found — check data"
    wrong = [j["job_id"] for j in attorney_jobs if j.get("professional_staff") != "professional"]
    assert wrong == [], f"Attorney jobs with wrong professional_staff: {wrong[:5]}"


def test_jd_credential_in_description():
    """Jobs with JD/J.D. in description should have 'JD' in credentials_required."""
    jobs = _load_classified()
    import re
    jd_jobs = [j for j in jobs if re.search(r'\bJ\.?D\.?\b', j.get("description") or "")]
    if not jd_jobs:
        pytest.skip("No JD-mentioning jobs in current dataset")
    wrong = [j["job_id"] for j in jd_jobs if "JD" not in (j.get("credentials_required") or [])]
    assert wrong == [], f"Jobs with JD in desc but missing from credentials_required: {wrong[:5]}"


def test_temporary_title_employment_type():
    """Jobs with 'temporary' in title should have employment_type = 'temporary'."""
    jobs = _load_classified()
    import re
    temp_jobs = [j for j in jobs if re.search(r'\btemporary\b', j.get("title") or "", re.IGNORECASE)]
    assert temp_jobs, "No temporary jobs found — check data"
    wrong = [j["job_id"] for j in temp_jobs if j.get("employment_type") != "temporary"]
    assert wrong == [], f"Temporary jobs with wrong employment_type: {wrong[:5]}"


def test_intelligence_card_fields_populated():
    """All jobs in classified_jobs.json should have all intelligence card fields present."""
    jobs = _load_classified()
    required_fields = [
        "union_affiliation", "employment_type", "supervisory",
        "professional_staff", "credentials_required", "benefits_signals",
        "years_experience", "background_required",
    ]
    missing = []
    for j in jobs:
        for field in required_fields:
            if field not in j:
                missing.append((j.get("job_id"), field))
    assert missing == [], f"Jobs missing intelligence card fields: {missing[:10]}"
