"""
Regression tests for the deterministic rules classifier.

Ground truth: the 10 spot-check jobs validated during the 2026-05-28 review session,
plus targeted edge cases for each failure mode that was diagnosed and fixed.

Run with:
    pytest tests/test_classifier.py
    pytest tests/test_classifier.py -v          # verbose output
    pytest tests/test_classifier.py -k senior   # run a subset by keyword
"""
import pytest

from pipeline.classify_jobs_rules import (
    classify_experience,
    classify_job_function,
    classify_location_parsed,
    classify_location_type,
)


# ---------------------------------------------------------------------------
# Helper — build a minimal job dict for the classifier functions
# ---------------------------------------------------------------------------
def job(
    title="",
    exp_level=None,
    role_type=None,
    location_raw="",
    city=None,
    state_abbr=None,
    is_remote=False,
    description=None,
    source_board="unionjobs.com",
):
    return {
        "title": title,
        "exp_level": exp_level,
        "role_type": role_type,
        "location_raw": location_raw,
        "city": city,
        "state_abbr": state_abbr,
        "is_remote": is_remote,
        "description": description,
        "source_board": source_board,
    }


# ===========================================================================
# EXPERIENCE LEVEL — classify_experience()
# ===========================================================================

# ── Spot-check ground truth (10 jobs) ──────────────────────────────────────
SPOT_CHECK_EXP = [
    # (job_kwargs, expected_level, test_id)
    pytest.param(
        dict(title="Union Organizer (Internal Public Sector)", exp_level=2, role_type="Union job"),
        "early-career",
        id="spot-01-union-organizer",
    ),
    pytest.param(
        dict(title="In-House Legal Counsel", exp_level=2, role_type="Legal"),
        "experienced",
        id="spot-02-legal-counsel",
    ),
    pytest.param(
        # Fixed failure mode: "Senior" alone should NOT elevate to leadership.
        dict(title="Senior Field Representative Political and Field Mobilization Hub",
             exp_level=3, role_type="Union job"),
        "experienced",
        id="spot-03-senior-field-rep-not-leadership",
    ),
    pytest.param(
        dict(title="Collective Bargaining Specialist", exp_level=2, role_type="Union job"),
        "experienced",
        id="spot-04-collective-bargaining-specialist",
    ),
    pytest.param(
        # Arena title with embedded employer; exp=4 maps to experienced (no strong title signal)
        dict(title="The Wisco Project: Special Programming Director - The Wisco Project",
             exp_level=4, role_type="Union job"),
        "leadership",
        id="spot-05-wisco-special-programming-director",
    ),
    pytest.param(
        # Arena title; exp=4 + no director/VP/chief → experienced
        dict(title="ALASKA WILDERNESS LEAGUE: Regional Organizing Manager Maine/New Hampshire",
             exp_level=4, role_type="Union job"),
        "experienced",
        id="spot-06-alaska-wilderness-organizing-manager",
    ),
    pytest.param(
        # Fixed failure mode: speechwriter → experienced (not influenced by "Executive" prefix
        # since EXEC_ADMIN_ASSISTANT_RE fires, not LEAD_STRONG).
        # Actual: exp=4 → experienced, and EXEC_ADMIN_ASSISTANT_RE doesn't match → exp=4 fallback.
        dict(title="Executive Speechwriter", exp_level=4, role_type="Union job"),
        "experienced",
        id="spot-07-executive-speechwriter",
    ),
    pytest.param(
        dict(title="Member Outreach Manager Organizing and Member Engagement",
             exp_level=4, role_type="Union job"),
        "experienced",
        id="spot-08-member-outreach-manager",
    ),
    pytest.param(
        # LEAD_MOD_RE matches "Director" (not followed by "of") → leadership
        dict(title="Strategic Campaigns Director Department of Research and Public Policy",
             exp_level=4, role_type="Admin/operations"),
        "leadership",
        id="spot-09-strategic-campaigns-director",
    ),
    pytest.param(
        # exp=4 + Admin/operations + no director/VP → experienced
        dict(title="Operations Manager", exp_level=4, role_type="Admin/operations"),
        "experienced",
        id="spot-10-operations-manager",
    ),
]


@pytest.mark.parametrize("kwargs,expected_level", SPOT_CHECK_EXP)
def test_spot_check_experience_level(kwargs, expected_level):
    level, _conf = classify_experience(job(**kwargs))
    assert level == expected_level


# ── Edge cases: leadership signals ─────────────────────────────────────────
@pytest.mark.parametrize("title,expected_level", [
    ("Vice President of Organizing",                  "leadership"),
    ("Vice-President for Strategic Campaigns",        "leadership"),
    ("Executive Director of Organizing",              "leadership"),
    ("Director of Research and Public Policy",        "leadership"),
    ("Chief of Staff",                                "leadership"),
    ("Chief Financial Officer",                       "leadership"),
    ("General Counsel",                               "leadership"),
    ("Associate General Counsel",                     "leadership"),   # "general counsel" in LEAD_STRONG
    ("Deputy Director of Field Operations",           "leadership"),   # director of X
    ("President, SEIU Local 99",                      "leadership"),
], ids=[
    "vp-organizing", "vice-president-hyphen", "executive-director",
    "director-of-x", "chief-of-staff", "cfo", "general-counsel",
    "associate-general-counsel", "deputy-director-of", "president-local",
])
def test_leadership_signals(title, expected_level):
    level, _conf = classify_experience(job(title=title, exp_level=3))
    assert level == expected_level


# ── Edge cases: senior WITHOUT director/VP/chief stays experienced ──────────
@pytest.mark.parametrize("title", [
    "Senior Field Representative Political and Field Mobilization Hub",
    "Senior Office Administrator Political and Field Mobilization Hub",
    "Senior Strategist II Data & Analytics Department",
    "Senior Benefits Assistant – Pension UFCW Benefits Office",
    "Senior Political Coordinator Legislative and Political Action Department",
], ids=[
    "senior-field-rep", "senior-office-admin", "senior-strategist",
    "senior-benefits-assistant", "senior-political-coordinator",
])
def test_senior_without_director_is_not_leadership(title):
    """Bare 'Senior' prefix must not elevate to leadership."""
    level, _conf = classify_experience(job(title=title, exp_level=3, role_type="Union job"))
    assert level != "leadership", f"'{title}' should not be leadership"


# ── Edge cases: new-to-labor bucket ────────────────────────────────────────
@pytest.mark.parametrize("title,exp_level,role_type", [
    ("Union Organizer Fellowship",                     2, "External organizer"),
    ("Teamster Organizing Fellowship",                 2, "External organizer"),
    ("Organizing Internship",                          1, "External organizer"),
    ("Organizer Internship External Organizing Dept",  1, "External organizer"),
    ("Organizing Apprenticeship",                      1, "External organizer"),
    ("Hospitality Union Organizing Apprenticeship",    1, "External organizer"),
    ("Organizer-in-Training (Los Angeles)",            2, "External organizer"),
    ("Union Organizers-in-Training",                   1, "External organizer"),
    ("Government Affairs Fellow",                      2, "Union job"),
    ("Political & Legislative Advocacy Apprentice",    1, "Political/electoral"),
], ids=[
    "fellowship", "teamster-fellowship", "internship", "intern-ext-dept",
    "apprenticeship", "hospitality-apprenticeship", "organizer-in-training",
    "organizers-in-training", "govt-fellow", "political-apprentice",
])
def test_new_to_labor_title_signals(title, exp_level, role_type):
    level, _conf = classify_experience(job(title=title, exp_level=exp_level, role_type=role_type))
    assert level == "new-to-labor", f"'{title}' should be new-to-labor, got '{level}'"


def test_new_to_labor_description_signal():
    """Description containing 'no experience required' triggers new-to-labor."""
    j = job(
        title="Field Coordinator",
        exp_level=2,
        role_type="External organizer",
        description="We are hiring a Field Coordinator. No experience required. Recent graduates welcome.",
    )
    level, conf = classify_experience(j)
    assert level == "new-to-labor"
    assert conf == 0.7


# ── New-to-labor fires before leadership signals ────────────────────────────
def test_new_to_labor_overrides_leadership_words_in_title():
    """A 'Director Fellowship' is new-to-labor, not leadership."""
    level, _conf = classify_experience(job(
        title="Executive Director Fellowship Program", exp_level=1, role_type="External organizer"
    ))
    assert level == "new-to-labor"


# ── Edge cases: early-career ────────────────────────────────────────────────
@pytest.mark.parametrize("title,exp_level,role_type", [
    ("Program Assistant",            1, "Union job"),
    ("Administrative Assistant",     1, "Admin/operations"),
    ("Office Assistant",             1, "Admin/operations"),
    ("Law Clerk",                    1, "Legal"),
    ("Organizer I",                  1, "External organizer"),  # Grade-I pattern
    ("Representative I",             1, "Union job"),
], ids=[
    "program-assistant", "admin-assistant", "office-assistant",
    "law-clerk", "organizer-grade-i", "rep-grade-i",
])
def test_early_career_signals(title, exp_level, role_type):
    level, _conf = classify_experience(job(title=title, exp_level=exp_level, role_type=role_type))
    assert level == "early-career"


# ===========================================================================
# JOB FUNCTION — classify_job_function()
# ===========================================================================

# ── Spot-check ground truth ─────────────────────────────────────────────────
SPOT_CHECK_FN = [
    pytest.param(
        dict(title="Union Organizer (Internal Public Sector)", role_type="Union job"),
        "organizing",
        id="spot-01-union-organizer-fn",
    ),
    pytest.param(
        # Fixed failure mode: speechwriter → communications (not organizing)
        dict(title="Executive Speechwriter", role_type="Union job"),
        "communications",
        id="spot-02-speechwriter-is-comms",
    ),
    pytest.param(
        dict(title="In-House Legal Counsel", role_type="Legal"),
        "legal",
        id="spot-03-legal-counsel-fn",
    ),
    pytest.param(
        dict(title="Collective Bargaining Specialist", role_type="Union job"),
        "organizing",
        id="spot-04-collective-bargaining-fn",
    ),
    pytest.param(
        # "special programming" keyword → political
        dict(title="The Wisco Project: Special Programming Director - The Wisco Project",
             role_type="Union job"),
        "political",
        id="spot-05-special-programming-political",
    ),
    pytest.param(
        # "organizing" keyword → organizing
        dict(title="ALASKA WILDERNESS LEAGUE: Regional Organizing Manager Maine/New Hampshire",
             role_type="Union job"),
        "organizing",
        id="spot-06-organizing-manager-fn",
    ),
    pytest.param(
        # "research" keyword in title → research
        dict(title="Strategic Campaigns Director Department of Research and Public Policy",
             role_type="Admin/operations"),
        "research",
        id="spot-07-research-keyword-fn",
    ),
    pytest.param(
        dict(title="Operations Manager", role_type="Admin/operations"),
        "operations",
        id="spot-08-operations-manager-fn",
    ),
    pytest.param(
        # "member outreach" keyword → organizing
        dict(title="Member Outreach Manager Organizing and Member Engagement", role_type="Union job"),
        "organizing",
        id="spot-09-member-outreach-fn",
    ),
    pytest.param(
        # "political" keyword → political
        dict(title="Senior Field Representative Political and Field Mobilization Hub",
             role_type="Union job"),
        "political",
        id="spot-10-political-keyword-fn",
    ),
]


@pytest.mark.parametrize("kwargs,expected_fn", SPOT_CHECK_FN)
def test_spot_check_job_function(kwargs, expected_fn):
    fn = classify_job_function(job(**kwargs))
    assert fn == expected_fn


# ── Fixed failure modes: communications keywords ────────────────────────────
@pytest.mark.parametrize("title", [
    "Executive Speechwriter",
    "Communications Director",
    "Press Secretary",
    "Creative Lead Digital Department",    # creative lead fix
    "Digital Director",
    "Social Media Manager",
    "Graphic Designer",
    "Copywriter",
], ids=[
    "speechwriter", "comms-director", "press-secretary",
    "creative-lead", "digital-director", "social-media",
    "graphic-designer", "copywriter",
])
def test_communications_keywords(title):
    fn = classify_job_function(job(title=title, role_type="Union job"))
    assert fn == "communications", f"'{title}' should be communications, got '{fn}'"


# ── Legal, finance, technology ──────────────────────────────────────────────
def test_attorney_is_legal():
    assert classify_job_function(job(title="Staff Attorney", role_type="Legal")) == "legal"


def test_paralegal_is_legal():
    assert classify_job_function(job(title="Paralegal", role_type="Legal")) == "legal"


def test_accountant_is_finance():
    assert classify_job_function(job(title="Accountant", role_type="Admin/operations")) == "finance"


def test_payroll_specialist_is_finance():
    assert classify_job_function(job(title="Payroll Specialist", role_type="Admin/operations")) == "finance"


def test_it_director_is_technology():
    assert classify_job_function(job(title="IT Director", role_type="Admin/operations")) == "technology"


# ── Organizing via role_type fallback ───────────────────────────────────────
def test_internal_organizer_role_type_fallback():
    # No keyword match → falls to role_type "Internal organizer" → organizing
    fn = classify_job_function(job(title="Canvasser", role_type="Internal organizer"))
    assert fn == "organizing"


# ===========================================================================
# LOCATION TYPE — classify_location_type()
# ===========================================================================

@pytest.mark.parametrize("location_raw,is_remote,expected_type", [
    ("Remote",                                  False, "remote"),
    ("remote",                                  False, "remote"),
    ("Oakland, CA / Remote",                    False, "remote"),
    ("Remote / Washington, DC",                 False, "remote"),
    ("Hybrid - Chicago, IL",                    False, "hybrid"),
    ("Chicago, IL (Hybrid)",                    False, "hybrid"),
    ("Washington, DC",                          False, "in-person"),
    ("Salem, OR",                               False, "in-person"),
    ("Campaign Washington, DC",                 False, "in-person"),
    ("the Northeast Region (CT, DE, MA...)",    False, "in-person"),
    # is_remote fallback when no keyword in raw string
    ("Oakland, CA",                             True,  "remote"),
    ("Unknown",                                 False, "in-person"),
], ids=[
    "remote-exact", "remote-lower", "oakland-slash-remote", "remote-slash-dc",
    "hybrid-dash", "hybrid-parens", "dc-in-person", "salem-in-person",
    "campaign-washington", "northeast-region", "is-remote-fallback", "unknown",
])
def test_location_type(location_raw, is_remote, expected_type):
    lt = classify_location_type(job(location_raw=location_raw, is_remote=is_remote))
    assert lt == expected_type


# ===========================================================================
# LOCATION PARSED — classify_location_parsed()
# ===========================================================================

def test_northeast_region_produces_no_state():
    """
    Fixed failure mode: 'the Northeast Region (CT, DE, MA...)' had state='DE'
    because the normalizer picked DE from the state list. classify_location_parsed
    must detect this as a regional string and return state=None, region='Northeast'.
    """
    lp = classify_location_parsed(job(
        location_raw="the Northeast Region (CT, DE, MA, MD/DC, ME, NH, NJ, NY, PA, RI, and VT) *must live within 100 miles of major airport*",
        city=None,
        state_abbr="DE",  # falsely scraped state — must be discarded
    ))
    assert lp["city"] is None
    assert lp["state"] is None
    assert lp["region"] == "Northeast"


def test_campaign_washington_city_sanitized():
    """
    Fixed failure mode: location_raw='Campaign Washington, DC' parsed by normalize_jobs.py
    to city='Campaign Washington'. classify_location_parsed must strip the leading
    noise word and return city='Washington'.
    """
    lp = classify_location_parsed(job(
        location_raw="Campaign Washington, DC",
        city="Campaign Washington",
        state_abbr="DC",
    ))
    assert lp["city"] == "Washington"
    assert lp["state"] == "DC"
    assert lp["region"] == "Mid-Atlantic"


def test_clean_city_state_preserved():
    """Standard 'City, ST' location passes through unchanged."""
    lp = classify_location_parsed(job(
        location_raw="Oakland, CA",
        city="Oakland",
        state_abbr="CA",
    ))
    assert lp["city"] == "Oakland"
    assert lp["state"] == "CA"
    assert lp["region"] == "Bay Area"


def test_remote_to_start_city_nulled():
    """
    'Remote to start but must be in Oakland, CA' produces garbled city.
    It should be sanitized to city=None (remote jobs shouldn't have a city).
    """
    lp = classify_location_parsed(job(
        location_raw="Remote to start but must be in Oakland, CA",
        city="Remote to start but must be in Oakland",
        state_abbr="CA",
    ))
    assert lp["city"] is None
    # State may still be set (correct) since location will ultimately be CA
    assert lp["state"] == "CA"


def test_pure_remote_no_city_no_state():
    lp = classify_location_parsed(job(
        location_raw="Remote",
        city=None,
        state_abbr=None,
    ))
    assert lp["city"] is None
    assert lp["state"] is None
    assert lp["region"] is None


def test_washington_dc_has_airports():
    lp = classify_location_parsed(job(
        location_raw="Washington, DC",
        city="Washington",
        state_abbr="DC",
    ))
    assert "DCA" in lp["near_airports"]
    assert lp["region"] == "Mid-Atlantic"


def test_midwest_region_inferred():
    """Regional strings like 'the Midwest' should infer region without city/state."""
    lp = classify_location_parsed(job(
        location_raw="the Midwest Region",
        city=None,
        state_abbr="IL",  # falsely scraped
    ))
    assert lp["city"] is None
    assert lp["state"] is None
    assert lp["region"] == "Midwest"
