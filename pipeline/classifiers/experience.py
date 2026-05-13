"""
Experience level classifier — ported from getExpLevel() in output/jobs.html.

exp_level is integer 1–4:
  1 = Entry level
  2 = Organizer (mid, default)
  3 = Lead / Coordinator
  4 = Director / Manager

The known seniority bug in the JS (returning 'staff' string) is fixed here:
all roles get an integer 1–4. Role-type-based defaults handle non-organizing roles.
"""
import re
from typing import Tuple

# Patterns — ported verbatim from JS getExpLevel() word-boundary regexes.
# Applied to title only (experience is almost always signaled in the title).
_LEVEL_4_RE = re.compile(
    r'\b(director|manager|vice[\s-]?president|\bvp\b|chief|executive|president)\b',
    re.IGNORECASE
)
_LEVEL_3A_RE = re.compile(
    r'\b(coordinator|supervisor|advocate)\b',
    re.IGNORECASE
)
_LEVEL_3B_RE = re.compile(
    r'\b(lead|senior|\bsr\.?\b)\b',
    re.IGNORECASE
)
_LEVEL_1_RE = re.compile(
    r'\b(fellow|intern|internship|fellowship|apprentice|apprenticeship'
    r'|entry[\s-]level|associate\s+organizer|new\s+organizer|junior)\b',
    re.IGNORECASE
)


def classify_experience(title: str, description: str, role_type: str) -> Tuple[int, float]:
    """
    Returns (exp_level, confidence).
    exp_level: integer 1–4.
    confidence: 1.0 explicit title match, 0.6 role-type derived, 0.5 default fallback.
    """
    title = title or ''
    role_type = role_type or ''

    # Level 4 — always checked first (director/manager outranks everything)
    if _LEVEL_4_RE.search(title):
        return 4, 1.0

    # Level 3
    if _LEVEL_3A_RE.search(title) or _LEVEL_3B_RE.search(title):
        return 3, 1.0

    # Level 1 — entry signals in title
    if _LEVEL_1_RE.search(title):
        return 1, 1.0

    # Apprenticeship role type always maps to Level 1
    if role_type == 'Apprenticeship':
        return 1, 0.6

    # Union job (rank-and-file) → Level 2
    if role_type == 'Union job':
        return 2, 0.6

    # Default — mid-level organizer or staff
    return 2, 0.5


if __name__ == '__main__':
    cases = [
        # title,                        description, role_type,              exp exp_conf
        ('Executive Director',          '',          'Admin/operations',     4,  1.0),
        ('Senior Organizer',            '',          'External organizer',   3,  1.0),
        ('Lead Organizer',              '',          'External organizer',   3,  1.0),
        ('Coordinator',                 '',          'Internal organizer',   3,  1.0),
        ('Intern',                      '',          'Union job',            1,  1.0),
        ('Entry-Level Organizer',       '',          'External organizer',   1,  1.0),
        ('Apprenticeship Program',      '',          'Apprenticeship',       1,  1.0),
        ('Organizer',                   '',          'Apprenticeship',       1,  0.6),
        ('Organizer',                   '',          'Union job',            2,  0.6),
        ('Organizer',                   '',          'External organizer',   2,  0.5),
        ('Communications Staff',        '',          'Communications',       2,  0.5),
        ('Vice President of Organizing','',          'Internal organizer',   4,  1.0),
    ]
    passed = 0
    for title, desc, role_type, exp_lvl, exp_conf in cases:
        lvl, conf = classify_experience(title, desc, role_type)
        ok = lvl == exp_lvl and conf == exp_conf
        if not ok:
            print(f'FAIL: {title!r} role={role_type!r}')
            print(f'  expected ({exp_lvl}, {exp_conf}), got ({lvl}, {conf})')
        else:
            passed += 1
    print(f'{passed}/{len(cases)} passed')
