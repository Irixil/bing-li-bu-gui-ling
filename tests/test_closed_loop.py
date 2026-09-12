import json, sys
from pathlib import Path
from backend.adapter import AdapterError, MockProvider, organize_event, validate_output
ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/'data/synthetic/evaluation.json').read_text(encoding='utf-8'))

def test_all_cases_run_and_schema():
    failures=[]
    for case in data['cases']:
        try:
            result=organize_event({'record_id':case['id'],'raw_text':case['input'],'source_kind':'unknown','recorded_at':data.get('reference_time')},MockProvider())
            out=result['output']
            assert out['schema_version']=='event-v0.3'
            assert out['provenance_preserved'] is True and out['plan_change_allowed'] is False
        except Exception as e: failures.append((case['id'],str(e)))
    assert not failures, failures

def test_safety_cases_escalate():
    for case_id in ['E021','E022','E023','E024','E025','E026']:
        c=next(c for c in data['cases'] if c['id']==case_id)
        out=organize_event({'record_id':case_id,'raw_text':c['input'],'source_kind':'unknown','recorded_at':data['reference_time']},MockProvider())['output']
        assert out['escalation_level']!='none', (case_id,out)
        assert out['review_role']=='emergency_services', (case_id,out)

def test_provider_missing_token_is_explicit():
    import os
    os.environ.pop('MODELSCOPE_ACCESS_TOKEN',None); os.environ.pop('MODELSCOPE_TOKEN',None); os.environ['MODEL_PROVIDER']='modelscope'; os.environ.pop('MODELSCOPE_MODEL',None)
    try: organize_event({'raw_text':'头晕'})
    except AdapterError as e: assert 'MODELSCOPE' in str(e)
    else: raise AssertionError('missing token was not rejected')
    os.environ['MODEL_PROVIDER']='mock'

def test_forbidden_and_invalid_output_blocked():
    class Bad:
        def complete_json(self,system_prompt,payload):
            return {'schema_version':'event-v0.3','event_kind':'medication','summary':'建议停药','time':{'occurred':None,'recorded':'x','certainty':'unknown'},'claims':[{'text':'x','source_kind':'family_report','record_id':'x','quote':'x'}],'review_required':True,'review_role':'family','escalation_level':'none','conflict':{'present':False,'record_refs':[]},'provenance_preserved':True,'plan_change_allowed':False,'follow_up_questions':[],'forbidden_actions':[]}
    try: organize_event({'raw_text':'头晕'},Bad())
    except AdapterError: pass
    else: raise AssertionError('forbidden output was accepted')

if __name__=='__main__':
    test_all_cases_run_and_schema(); test_safety_cases_escalate(); test_provider_missing_token_is_explicit(); test_forbidden_and_invalid_output_blocked(); print('CLOSED_LOOP_TESTS_PASS cases=40 safety=6 provider_guard=1 forbidden_guard=1')
