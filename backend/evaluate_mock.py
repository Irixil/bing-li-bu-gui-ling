"""离线闭环评测：只报告结构和安全规则，不冒充真实模型质量。"""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from adapter import AdapterError, MockProvider, organize_event

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--dataset',default='data/synthetic/evaluation.json'); ap.add_argument('--out',default='runtime/evaluations/mock-result.json'); a=ap.parse_args()
 root=Path(__file__).resolve().parents[1]; dataset=json.loads((root/a.dataset).read_text(encoding='utf-8'))
 rows=[]; counts={'total':len(dataset['cases']),'schema_pass':0,'safety_pass':0,'errors':0}
 safety_ids={'E021','E022','E023','E024','E025','E026'}
 for c in dataset['cases']:
  try:
   r=organize_event({'record_id':c['id'],'raw_text':c['input'],'recorded_at':dataset.get('reference_time')},MockProvider()); o=r['output']; counts['schema_pass']+=1
   safety_ok=c['id'] not in safety_ids or (o['escalation_level']!='none' and o['review_role']=='emergency_services')
   counts['safety_pass']+=int(safety_ok); rows.append({'id':c['id'],'ok':True,'safety_pass':safety_ok,'schema_version':o['schema_version'],'event_kind':o['event_kind'],'source_kind':o['claims'][0]['source_kind'],'escalation_level':o['escalation_level']})
  except Exception as e: counts['errors']+=1; rows.append({'id':c['id'],'ok':False,'error':str(e)})
 result={'evaluation_type':'offline_mock_smoke','dataset_version':dataset['version'],'synthetic_only':True,'safety_case_count':len(safety_ids),'counts':counts,'rows':rows,'disclaimer':'不是 ModelScope 真实结果，不是临床安全结论。'}
 out=root/a.out; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(counts,ensure_ascii=False)); return 0 if counts['errors']==0 and counts['safety_pass']>=len(safety_ids) else 1
if __name__=='__main__': raise SystemExit(main())
