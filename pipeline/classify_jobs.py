"""
Classify normalized jobs: fill sector, role_type, exp_level, special_requirements.

Usage:
    python -m pipeline.classify_jobs [--input PATH] [--output PATH]

Defaults:
    --input   data/normalized_jobs.json
    --output  data/classified_jobs.json
"""
import argparse
import json
from collections import Counter
from typing import Optional

from pipeline.classifiers.sector import classify_sector, classify_sector_all, SECTOR_SVS
from pipeline.classifiers.role_type import classify_role_type
from pipeline.classifiers.experience import classify_experience
from pipeline.classifiers.special_requirements import extract_special_requirements

# Sectors where is_mcalevey_priority = True (SVS >= 75)
MCALEVEY_SECTORS = {'Healthcare', 'Education', 'Public Sector', 'Logistics'}

# Map new role_type values to rf_subtype_label for frontend display
RF_SUBTYPE_LABELS = {
    'Internal organizer':  'Internal Organizer',
    'External organizer':  'External Organizer',
    'Communications':      'Communications',
    'Legal':               'Legal',
    'Research':            'Research',
    'Political/electoral': 'Political & Electoral',
    'Admin/operations':    'Admin & Operations',
    'Apprenticeship':      'Apprenticeship',
    'Union job':           'Union Job',
}

LOW_CONF_THRESHOLD = 0.5


def classify_job(job: dict) -> dict:
    title = job.get('title') or ''
    description = job.get('description') or ''

    sector, sector_conf = classify_sector(title, description)
    role_type, role_conf = classify_role_type(title, description)
    exp_level, exp_conf = classify_experience(title, description, role_type)
    special_reqs = extract_special_requirements(description)

    # Fields from normalizer that may already be set (manual overrides)
    sector = job.get('sector') or sector
    role_type = job.get('role_type') or role_type
    exp_level = job.get('exp_level') or exp_level

    # Derived display/filter fields for the frontend
    svs_score = SECTOR_SVS.get(sector, 10) if sector else 10
    is_mcalevey_priority = sector in MCALEVEY_SECTORS if sector else False
    rf_subtype_label = RF_SUBTYPE_LABELS.get(role_type, role_type)

    # Low confidence flags
    low_confidence = []
    if sector_conf < LOW_CONF_THRESHOLD:
        low_confidence.append('sector')
    if role_conf < LOW_CONF_THRESHOLD:
        low_confidence.append('role_type')
    if exp_conf < LOW_CONF_THRESHOLD:
        low_confidence.append('exp_level')

    return {
        **job,
        'sector':               sector,
        'role_type':            role_type,
        'exp_level':            exp_level,
        'special_requirements': special_reqs if not job.get('special_requirements') else job['special_requirements'],
        # Frontend compatibility fields
        'svs_score':            svs_score,
        'is_mcalevey_priority': is_mcalevey_priority,
        'rf_subtype_label':     rf_subtype_label,
        'sector_tags':          [sector] if sector else [],
        # Classifier metadata (rules engine uses these)
        '_confidences':         {'sector': sector_conf, 'role_type': role_conf, 'exp_level': exp_conf},
        '_sector_confidences':  classify_sector_all(title, description),
        'low_confidence':       low_confidence,
    }


def recompute_derived(job: dict) -> dict:
    """
    Recompute frontend/display fields after rule application has potentially changed
    sector, role_type, or exp_level. Called by reclassify.py after rules are applied.
    """
    sector = job.get('sector')
    role_type = job.get('role_type')
    confidences = job.get('_confidences', {})

    svs_score = SECTOR_SVS.get(sector, 10) if sector else 10
    is_mcalevey_priority = sector in MCALEVEY_SECTORS if sector else False
    rf_subtype_label = RF_SUBTYPE_LABELS.get(role_type, role_type or '')
    sector_tags = [sector] if sector else []

    low_confidence = []
    if confidences.get('sector', 0.0) < LOW_CONF_THRESHOLD:
        low_confidence.append('sector')
    if confidences.get('role_type', 0.0) < LOW_CONF_THRESHOLD:
        low_confidence.append('role_type')
    if confidences.get('exp_level', 0.0) < LOW_CONF_THRESHOLD:
        low_confidence.append('exp_level')

    return {
        **job,
        'svs_score':            svs_score,
        'is_mcalevey_priority': is_mcalevey_priority,
        'rf_subtype_label':     rf_subtype_label,
        'sector_tags':          sector_tags,
        'low_confidence':       low_confidence,
    }


def main():
    parser = argparse.ArgumentParser(description='Classify normalized job objects')
    parser.add_argument('--input',  default='data/normalized_jobs.json')
    parser.add_argument('--output', default='data/classified_jobs.json')
    args = parser.parse_args()

    with open(args.input, encoding='utf-8') as f:
        jobs = json.load(f)

    classified = [classify_job(j) for j in jobs]

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(classified, f, indent=2, ensure_ascii=False)

    # Report
    sector_counts: Counter = Counter(j['sector'] or 'Unknown' for j in classified)
    role_counts: Counter = Counter(j['role_type'] or 'Unknown' for j in classified)
    exp_counts: Counter = Counter(j['exp_level'] for j in classified)
    low_conf: Counter = Counter(field for j in classified for field in j['low_confidence'])
    flagged = sum(1 for j in classified if j['low_confidence'])

    print(f'Classified: {len(classified)} jobs')
    print(f'Sector breakdown: {dict(sector_counts.most_common())}')
    print(f'Role type breakdown: {dict(role_counts.most_common())}')
    print(f'Exp level breakdown: {dict(sorted(exp_counts.items()))}')
    print(f'Low confidence flags: {dict(low_conf.most_common())}')
    print(f'Total jobs flagged for review: {flagged}')


if __name__ == '__main__':
    main()
