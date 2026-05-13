"""
Sector classifier — ported verbatim from classifyJob() in output/jobs.html.

Sectors (in declared order for tie-breaking):
  Healthcare, Education, Logistics, Public Sector, Building Trades, Manufacturing
"""
import re
from typing import Optional, Tuple

# Patterns ported verbatim from JS classifyJob() sector_tags detection.
# Each value is (title_pattern, combined_pattern) — same regex, applied to
# title alone (confidence 1.0) or title+description (confidence 0.7).
_SECTOR_PATTERNS = [
    ('Healthcare',      re.compile(r'nurs|health|hospital|medical|patient|pharmac|dental|clinic|ems|ambulanc|care worker|home care', re.IGNORECASE)),
    ('Education',       re.compile(r'teacher|school|education|faculty|professor|tutor|instruct|k-12|k12|higher ed|university|college', re.IGNORECASE)),
    ('Logistics',       re.compile(r'warehouse|logistics|shipping|trucking|transport|driver|freight|supply chain|port|dock|longshore', re.IGNORECASE)),
    ('Public Sector',   re.compile(r'municipal|county gov|public sector|government|state worker|public employee|civil service', re.IGNORECASE)),
    ('Building Trades', re.compile(r'construction|building trade|electrician|plumber|carpenter|iron worker|pipefitter|sheet metal|hvac|tile|bricklayer', re.IGNORECASE)),
    ('Manufacturing',   re.compile(r'manufactur|factory|plant|production|assembly|steel|auto worker|machinist', re.IGNORECASE)),
]

# Strategic value scores — same as JS SECTOR_SVS
SECTOR_SVS = {
    'Healthcare':      100,
    'Education':       100,
    'Public Sector':   100,
    'Logistics':        75,
    'Building Trades':  50,
    'Manufacturing':    25,
}


def classify_sector_all(title: str, description: str) -> dict:
    """
    Returns {sector: confidence} for ALL sectors (0.0 if no match).
    Used by the rules engine to apply keyword boosts/penalizes.
    """
    title = title or ''
    description = description or ''
    combined = title + ' ' + description
    result = {}
    for sector, pattern in _SECTOR_PATTERNS:
        if pattern.search(title):
            result[sector] = 1.0
        elif pattern.search(combined):
            result[sector] = 0.7
        else:
            result[sector] = 0.0
    return result


def classify_sector(title: str, description: str) -> Tuple[Optional[str], float]:
    """
    Returns (sector, confidence).
    confidence: 1.0 title match, 0.7 description-only match, 0.0 no match (None).
    If multiple match, return highest confidence; tie → first in declared order.
    """
    title = title or ''
    description = description or ''
    combined = title + ' ' + description

    best_sector: Optional[str] = None
    best_conf: float = 0.0

    for sector, pattern in _SECTOR_PATTERNS:
        if pattern.search(title):
            conf = 1.0
        elif pattern.search(combined):
            conf = 0.7
        else:
            continue

        if conf > best_conf:
            best_sector = sector
            best_conf = conf

    return best_sector, best_conf


if __name__ == '__main__':
    cases = [
        ('RN Organizer',                        'Organize hospital nurses',        'Healthcare',      0.7),
        ('Healthcare Organizer',                '',                                'Healthcare',      1.0),
        ('Field Organizer',                      'Organize warehouse workers',      'Logistics',       0.7),
        ('Political Director',                   'Run electoral campaigns',         None,              0.0),
        ('Education Organizer',                  'Work with teachers',              'Education',       1.0),
        ('Organizer',                            'Construction and building trades','Building Trades', 0.7),
        ('Director of Manufacturing Operations', '',                                'Manufacturing',   1.0),
        ('Organizer',                            '',                                None,              0.0),
    ]
    passed = 0
    for title, desc, exp_sector, exp_conf in cases:
        sector, conf = classify_sector(title, desc)
        ok = sector == exp_sector and conf == exp_conf
        if not ok:
            desc_snip = repr(desc[:40])
            print(f'FAIL: {title!r} + {desc_snip}')
            print(f'  expected ({exp_sector}, {exp_conf}), got ({sector}, {conf})')
        else:
            passed += 1
    print(f'{passed}/{len(cases)} passed')
