import sys
from pathlib import Path
from backend.adapter import AdapterError, MockProvider, organize_event

def test_mock_extracts_source_and_danger():
    out=organize_event({'record_id':'t1','raw_text':'女儿：妈妈胸痛，问要不要先停药？','source_kind':'family_observation','recorded_at':'2026-04-21T12:00:00+08:00'},MockProvider())['output']
    assert out['claims'][0]['source_kind']=='family_observation'
    assert out['escalation_level']=='emergency' and out['review_role']=='emergency_services'
    assert out['plan_change_allowed'] is False

def test_empty_input_rejected():
    try: organize_event({'raw_text':'   '},MockProvider())
    except AdapterError: return
    raise AssertionError('空输入未被拒绝')

def test_forbidden_model_output_rejected():
    class Bad:
      def complete_json(self,system_prompt,payload):
        return {'schema_version':'event-v0.3','event_kind':'medication','summary':'建议停药','time':{'occurred':None,'recorded':'x','certainty':'unknown'},'claims':[{'text':'x','source_kind':'family_report','record_id':'x','quote':'x'}],'review_required':True,'review_role':'family','escalation_level':'none','conflict':{'present':False,'record_refs':[]},'provenance_preserved':True,'plan_change_allowed':False,'follow_up_questions':[],'forbidden_actions':[]}
    try: organize_event({'raw_text':'头晕'},Bad())
    except AdapterError: return
    raise AssertionError('越权输出未被拦截')
if __name__=='__main__':
 test_mock_extracts_source_and_danger();test_empty_input_rejected();test_forbidden_model_output_rejected();print('adapter tests: PASS')
