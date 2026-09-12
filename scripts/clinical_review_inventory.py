"""Local review-work inventory; never a diagnosis, runtime rule, or acceptance gate."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from backend.safety import scan_danger

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASETS = ('data/synthetic/evaluation.json', 'data/synthetic/c-model-smoke.json',
                    'data/public_cases/cases.json')


def build_inventory(registry, datasets):
    items = registry['items']
    ids = [item['id'] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate review item ID')
    compiled = {item['id']: [re.compile(p, re.I) for p in item.get('topic_patterns', [])]
                for item in items}
    rows = []
    counts = Counter()
    for source, dataset in datasets:
        for case in dataset['cases']:
            raw = case['input']
            text = unicodedata.normalize('NFKC', raw)
            safety = scan_danger(raw)
            runtime_ids = set(safety['matched_rules'] + safety['clinical_review_flags'])
            matched = [item['id'] for item in items
                       if runtime_ids.intersection(item.get('runtime_rule_ids', []))
                       or any(p.search(text) for p in compiled[item['id']])]
            counts.update(matched)
            rows.append({'dataset': source, 'case_id': case['id'],
                         'raw_text_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                         'review_item_ids': matched,
                         'runtime_matched_rules': safety['matched_rules'],
                         'runtime_clinical_review_flags': safety['clinical_review_flags'],
                         'status': 'needs_medical_review' if matched else 'no_topic_match'})
    return {'report_type': 'offline_clinical_review_inventory',
            'registry_version': registry.get('version'), 'runtime_mutations': False,
            'medical_signoff': 'pending', 'case_count': len(rows),
            'flagged_case_count': sum(bool(row['review_item_ids']) for row in rows),
            'item_case_counts': {item['id']: counts[item['id']] for item in items},
            'rows': rows,
            'note': '话题/规则匹配仅用于研发复核排队，包含历史、否定和假设；'
                    '无匹配不代表正常、覆盖完整或医学审核通过。未修改输入数据或运行时规则。'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', action='append', help='Repeat for several local JSON datasets')
    parser.add_argument('--out', default='runtime/evaluations/clinical-review-inventory.json')
    args = parser.parse_args(argv)
    registry = json.loads((ROOT / 'config/clinical-review-backlog.json').read_text())
    datasets = [(path, json.loads((ROOT / path).read_text()))
                for path in (args.dataset or DEFAULT_DATASETS)]
    report = build_inventory(registry, datasets)
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'case_count': report['case_count'],
                      'flagged_case_count': report['flagged_case_count'],
                      'review_items': len(registry['items']), 'medical_signoff': 'pending'}))


if __name__ == '__main__':
    main()
