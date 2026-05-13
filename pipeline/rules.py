"""
Rule application logic for the reclassify pipeline.

Rule priority (highest to lowest):
  1. manual   — per job_id, full override of specified fields
  2. employers — per employer name, overrides specified fields
  3. keywords  — boost/penalize sector confidence, re-pick best sector
  4. role_keywords — override role_type if keyword matches
  5. hide_keywords — set hidden=True if any keyword matches title+description

All functions are pure (return new dict, do not mutate input).
"""
import json
import os
from typing import Optional

_EMPTY_RULES = {
    "manual": {},
    "employers": {},
    "keywords": {
        "Healthcare":      {"boost": [], "penalize": []},
        "Education":       {"boost": [], "penalize": []},
        "Logistics":       {"boost": [], "penalize": []},
        "Public Sector":   {"boost": [], "penalize": []},
        "Building Trades": {"boost": [], "penalize": []},
        "Manufacturing":   {"boost": [], "penalize": []},
    },
    "role_keywords": {
        "Internal organizer": [], "External organizer": [], "Communications": [],
        "Legal": [], "Research": [], "Political/electoral": [],
        "Admin/operations": [], "Apprenticeship": [], "Union job": [],
    },
    "hide_keywords": [],
}


def load_rules(path: str) -> dict:
    """Load and validate rules.json. Returns empty scaffold if file missing."""
    if not os.path.exists(path):
        return _EMPTY_RULES
    with open(path, encoding='utf-8') as f:
        rules = json.load(f)
    # Ensure all top-level keys are present
    for key in _EMPTY_RULES:
        rules.setdefault(key, _EMPTY_RULES[key])
    return rules


def apply_manual_rule(job: dict, rule: dict) -> dict:
    """
    Apply a manual rule to a job. Overrides any specified classification fields.
    Handles: sector, role_type, exp_level, special_requirements,
             location_override, hide, boost.
    """
    overrides = {}

    for field in ('sector', 'role_type', 'exp_level', 'special_requirements'):
        if field in rule:
            overrides[field] = rule[field]
            # Manual overrides get maximum confidence so they don't get flagged low
            if field in ('sector', 'role_type', 'exp_level'):
                key = field if field != 'exp_level' else 'exp_level'
                new_confs = dict(job.get('_confidences', {}))
                new_confs[key] = 1.0
                overrides['_confidences'] = new_confs

    if 'location_override' in rule:
        overrides['location_raw'] = rule['location_override']

    if 'hide' in rule:
        overrides['hidden'] = bool(rule['hide'])

    if rule.get('boost'):
        overrides['boosted'] = True

    return {**job, **overrides}


def apply_employer_rule(job: dict, employer_rule: dict) -> dict:
    """
    Apply an employer rule to a job. Overrides sector and/or role_type.
    Sets confidence to 1.0 for overridden fields.
    """
    overrides = {}
    new_confs = dict(job.get('_confidences', {}))
    changed = False

    for field in ('sector', 'role_type', 'exp_level'):
        if field in employer_rule:
            overrides[field] = employer_rule[field]
            new_confs[field] = 1.0
            changed = True

    if not changed:
        return job

    return {**job, **overrides, '_confidences': new_confs}


def apply_keyword_rules(job: dict, keyword_rules: dict) -> dict:
    """
    Apply sector boost/penalize keyword rules.

    For each sector: if a boost keyword matches combined title+desc, add +0.3
    (cap 1.0). If a penalize keyword matches, subtract -0.3 (floor 0.0).
    After adjustments, re-pick the highest-confidence sector.
    """
    if not keyword_rules:
        return job

    combined = ((job.get('title') or '') + ' ' + (job.get('description') or '')).lower()
    confidences = dict(job.get('_sector_confidences', {}))
    if not confidences:
        return job

    changed = False
    for sector, rules in keyword_rules.items():
        for kw in (rules.get('boost') or []):
            if kw.lower() in combined:
                confidences[sector] = min(1.0, confidences.get(sector, 0.0) + 0.3)
                changed = True
        for kw in (rules.get('penalize') or []):
            if kw.lower() in combined:
                confidences[sector] = max(0.0, confidences.get(sector, 0.0) - 0.3)
                changed = True

    if not changed:
        return job

    # Pick new best sector
    best_sector: Optional[str] = None
    best_conf = 0.0
    for s, c in confidences.items():
        if c > best_conf:
            best_conf = c
            best_sector = s

    new_confs = {**job.get('_confidences', {}), 'sector': best_conf}
    return {
        **job,
        'sector': best_sector,
        '_sector_confidences': confidences,
        '_confidences': new_confs,
    }


def apply_role_keywords(job: dict, role_keyword_rules: dict) -> dict:
    """
    If any keyword in role_keyword_rules[role_type] matches title+description,
    override role_type. First match wins (check in dict insertion order).
    Confidence set to 0.8 (high but not 1.0, since it's a keyword rule not manual).
    """
    if not role_keyword_rules:
        return job

    combined = ((job.get('title') or '') + ' ' + (job.get('description') or '')).lower()

    for role_type, keywords in role_keyword_rules.items():
        for kw in (keywords or []):
            if kw.lower() in combined:
                new_confs = {**job.get('_confidences', {}), 'role_type': 0.8}
                return {**job, 'role_type': role_type, '_confidences': new_confs}

    return job


def check_hide(job: dict, hide_keywords: list) -> bool:
    """Return True if any hide keyword appears in title or description."""
    if not hide_keywords:
        return False
    combined = ((job.get('title') or '') + ' ' + (job.get('description') or '')).lower()
    return any(kw.lower() in combined for kw in hide_keywords)
