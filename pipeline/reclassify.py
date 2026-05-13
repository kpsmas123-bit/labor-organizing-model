"""
Re-classify all jobs: run base classifier then apply rules.json overrides.

Usage:
    python -m pipeline.reclassify

Reads:  data/normalized_jobs.json + data/rules.json
Writes: data/classified_jobs.json
"""
import argparse
import json
from collections import Counter

from pipeline.classify_jobs import classify_job, recompute_derived
from pipeline.rules import (
    load_rules,
    apply_manual_rule,
    apply_employer_rule,
    apply_keyword_rules,
    apply_role_keywords,
    check_hide,
)


def main():
    parser = argparse.ArgumentParser(description='Re-classify jobs with rules applied')
    parser.add_argument('--input',   default='data/normalized_jobs.json')
    parser.add_argument('--rules',   default='data/rules.json')
    parser.add_argument('--output',  default='data/classified_jobs.json')
    args = parser.parse_args()

    with open(args.input, encoding='utf-8') as f:
        raw_jobs = json.load(f)

    rules = load_rules(args.rules)

    manual_rules    = rules.get('manual', {})
    employer_rules  = rules.get('employers', {})
    keyword_rules   = rules.get('keywords', {})
    role_kw_rules   = rules.get('role_keywords', {})
    hide_keywords   = rules.get('hide_keywords', [])

    # Summarize loaded rules
    kw_rule_count = sum(
        len(v.get('boost', [])) + len(v.get('penalize', []))
        for v in keyword_rules.values()
    )
    role_kw_count = sum(len(v) for v in role_kw_rules.values())
    print(
        f'Loaded: {len(raw_jobs)} jobs, '
        f'{len(manual_rules) + len(employer_rules) + kw_rule_count + role_kw_count + len(hide_keywords)} rules '
        f'(manual: {len(manual_rules)}, employers: {len(employer_rules)}, '
        f'keyword rules: {kw_rule_count}, role keywords: {role_kw_count}, '
        f'hide_keywords: {len(hide_keywords)})'
    )

    # Step 1: base classification
    classified = [classify_job(j) for j in raw_jobs]

    # Step 2: apply rules in priority order
    manual_applied   = 0
    employer_applied = 0
    keyword_changed  = 0
    role_kw_applied  = 0
    hidden_count     = 0
    boosted_count    = 0

    result = []
    for job in classified:
        job_id   = job.get('job_id', '')
        employer = (job.get('employer') or '').strip()

        if job_id in manual_rules:
            # Manual rule: highest priority, skip employer + keyword rules
            job = apply_manual_rule(job, manual_rules[job_id])
            manual_applied += 1
            if job.get('boosted'):
                boosted_count += 1
        else:
            # Employer rule
            if employer in employer_rules:
                job = apply_employer_rule(job, employer_rules[employer])
                employer_applied += 1

            # Keyword boost/penalize
            prev_sector = job.get('sector')
            job = apply_keyword_rules(job, keyword_rules)
            if job.get('sector') != prev_sector:
                keyword_changed += 1

            # Role keyword override
            prev_role = job.get('role_type')
            job = apply_role_keywords(job, role_kw_rules)
            if job.get('role_type') != prev_role:
                role_kw_applied += 1

        # Hide keywords apply to all jobs (including manual-ruled ones)
        if check_hide(job, hide_keywords):
            job = {**job, 'hidden': True}
            hidden_count += 1

        # Recompute derived display fields after rule application
        job = recompute_derived(job)
        result.append(job)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Report
    sector_counts: Counter = Counter(j['sector'] or 'Unknown' for j in result)
    role_counts:   Counter = Counter(j['role_type'] or 'Unknown' for j in result)
    exp_counts:    Counter = Counter(j['exp_level'] for j in result)
    low_conf_count = sum(1 for j in result if j.get('low_confidence'))

    print('Rule application:')
    print(f'  Manual overrides applied:       {manual_applied}')
    print(f'  Employer rules applied:          {employer_applied}')
    print(f'  Keyword boosts/penalizes:        {keyword_changed} sector changes')
    print(f'  Role keyword overrides:          {role_kw_applied}')
    print(f'  Jobs hidden:                     {hidden_count}')
    print(f'  Jobs boosted:                    {boosted_count}')
    print('Final breakdown:')
    print(f'  Sector:    {dict(sector_counts.most_common())}')
    print(f'  Role type: {dict(role_counts.most_common())}')
    print(f'  Exp level: {dict(sorted(exp_counts.items()))}')
    print(f'Low confidence (post-rules): {low_conf_count} flagged')


if __name__ == '__main__':
    main()
