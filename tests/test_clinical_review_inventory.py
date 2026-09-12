import copy
import json

from backend.safety import RULES
from scripts.clinical_review_inventory import ROOT, build_inventory


def test_batch_topics_do_not_turn_into_diagnoses_or_mutate_inputs():
    registry = json.loads((ROOT / 'config/clinical-review-backlog.json').read_text())
    dataset = {'cases': [
        {'id': 'same', 'input': '历史论文记录心率每分钟40次，情况未经核实。'},
        {'id': 'hypothesis', 'input': '如果血氧降低需要核对什么？'},
    ]}
    before = copy.deepcopy(dataset)
    report = build_inventory(registry, [('synthetic.json', dataset), ('public.json', dataset)])
    assert dataset == before
    assert report['case_count'] == 4
    assert report['medical_signoff'] == 'pending'
    assert report['runtime_mutations'] is False
    assert 'review_low_heart_rate_candidate' in report['rows'][0]['review_item_ids']
    assert 'review_oxygen_saturation_gap' in report['rows'][1]['review_item_ids']
    assert report['rows'][0]['dataset'] != report['rows'][2]['dataset']
    assert dataset['cases'][0]['input'] not in json.dumps(report, ensure_ascii=False)


def test_all_live_rules_have_unsigned_review_work_and_timing_stays_disabled():
    registry = json.loads((ROOT / 'config/clinical-review-backlog.json').read_text())
    refs = {ref for item in registry['items'] for ref in item['runtime_rule_ids']}
    assert refs == {name for name, _ in RULES} | {'extreme_pressure_number', 'low_heart_rate_candidate'}
    assert all(item['status'] == 'needs_medical_review' and item['medical_reviewer'] is None
               and item['medical_sources'] == [] for item in registry['items'])
    timing = json.loads((ROOT / 'config/transport-timing.placeholder.json').read_text())
    assert timing['runtime_enabled'] is False
    assert timing['collection'] == 'not_instrumented'
    assert all(value is None for value in timing['timings_ms'].values())
