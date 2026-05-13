"""
Role type classifier.

Role types (one only):
  Internal organizer, External organizer, Communications, Legal, Research,
  Political/electoral, Admin/operations, Apprenticeship, Union job

Keyword lists are at the top of this file — easy to edit.
"""
import re
from typing import Tuple

# ---------------------------------------------------------------------------
# Keyword lists — edit these to tune classification
# ---------------------------------------------------------------------------

# Apprenticeship detection — ported verbatim from JS classifyJob()
APPRENTICESHIP_PATTERN = re.compile(r'apprentic', re.IGNORECASE)

# Sub-type keyword lists (checked against title for conf 1.0, description for 0.7)
ROLE_KEYWORDS = {
    'Internal organizer': [
        'internal organizer', 'member organizer', 'shop steward training',
        'contract enforcement', 'internal organizing',
    ],
    'External organizer': [
        'external organizer', 'lead organizer', 'field organizer',
        'organize new', 'new workplace', 'external organizing',
        'new member organizer', 'new organizing',
    ],
    'Communications': [
        'communications', 'comms director', 'press secretary', 'media relations',
        'digital director', 'public relations', 'media director', 'press',
        'digital media', 'communications director',
    ],
    'Legal': [
        'attorney', 'counsel', 'legal director', 'paralegal',
        'labor counsel', 'legal assistant', 'general counsel',
    ],
    'Research': [
        'researcher', 'research analyst', 'policy research', 'data analyst',
        'research director', 'research associate', 'policy analyst',
        'research coordinator',
    ],
    'Political/electoral': [
        'political director', 'political organizer', 'electoral', 'campaign manager',
        'gotv', 'get out the vote', 'political action', 'political coordinator',
        'ballot', 'electoral campaign',
    ],
    'Admin/operations': [
        'office manager', 'operations', 'administrative', 'bookkeeper',
        'hr director', 'human resources', 'executive assistant', 'receptionist',
        'office assistant', 'payroll', 'accounting', 'finance director',
        'membership coordinator', 'database', 'it director', 'clerical',
    ],
}

# Compiled patterns per role type
_ROLE_PATTERNS = {
    role: re.compile('|'.join(re.escape(kw) for kw in kws), re.IGNORECASE)
    for role, kws in ROLE_KEYWORDS.items()
}

# Broad staff-role regex — ported verbatim from JS STAFF_ROLE_RE.
# Used as fallback: if none of the specific sub-types matched but this fires,
# the role is staff-type (assign Admin/operations, conf 0.5).
STAFF_ROLE_RE = re.compile(
    r'\b(receptionist|administrative|admin\b|office\s+manager|office\s+assistant'
    r'|executive\s+assistant|assistant\s+to|communications|comms\b|media\b'
    r'|digital\s+media|public\s+relations|research(?:er)?|analyst|data\s+analyst'
    r'|it\b|information\s+technology|tech\s+support|accountant|accounting'
    r'|finance|financial|payroll|paralegal|legal\b|attorney|counsel|lobbyist'
    r'|human\s+resources|\bhr\b|membership\s+rep|benefits|graphic|designer'
    r'|web\s+developer|database|clerical|bookkeeper|archivist|librarian'
    r'|translator|interpreter|events?\s+staff|fundrais)\b',
    re.IGNORECASE
)


def classify_role_type(title: str, description: str) -> Tuple[str, float]:
    """
    Returns (role_type, confidence).
    confidence: 1.0 title match, 0.7 description-only, 0.5 STAFF_ROLE_RE fallback, 0.3 default.
    """
    title = title or ''
    description = description or ''
    combined = title + ' ' + description

    # 1. Apprenticeship wins over everything
    if APPRENTICESHIP_PATTERN.search(combined):
        return 'Apprenticeship', 1.0

    # 2. Check specific sub-types — title first (1.0), then description (0.7)
    for role, pattern in _ROLE_PATTERNS.items():
        if pattern.search(title):
            return role, 1.0

    for role, pattern in _ROLE_PATTERNS.items():
        if pattern.search(description):
            return role, 0.7

    # 3. Broad staff-role fallback — we know it's a staff role but not which sub-type
    if STAFF_ROLE_RE.search(title):
        return 'Admin/operations', 0.5

    # 4. Default — likely an organizer role we couldn't sub-classify
    return 'Union job', 0.3


if __name__ == '__main__':
    cases = [
        ('Apprenticeship Organizer',    '',                             'Apprenticeship',       1.0),
        ('Lead Organizer',              'organize new workplace',       'External organizer',   1.0),
        ('Communications Director',     '',                             'Communications',       1.0),
        ('Staff Attorney',              '',                             'Legal',                1.0),
        ('Organizer',                   'internal organizing program',  'Internal organizer',   0.7),
        ('Data Analyst',                '',                             'Research',             1.0),
        ('Political Director',          '',                             'Political/electoral',  1.0),
        ('Office Manager',              '',                             'Admin/operations',     1.0),
        ('Organizer',                   '',                             'Union job',            0.3),
        # Admin/operations via explicit keyword list
        ('Receptionist',                '',                             'Admin/operations',     1.0),
        # STAFF_ROLE_RE fallback for a title not in explicit lists
        ('Lobbyist',                    '',                             'Admin/operations',     0.5),
    ]
    passed = 0
    for title, desc, exp_role, exp_conf in cases:
        role, conf = classify_role_type(title, desc)
        ok = role == exp_role and conf == exp_conf
        if not ok:
            print(f'FAIL: {title!r}')
            print(f'  expected ({exp_role}, {exp_conf}), got ({role}, {conf})')
        else:
            passed += 1
    print(f'{passed}/{len(cases)} passed')
