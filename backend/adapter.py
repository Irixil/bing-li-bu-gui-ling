from __future__ import annotations
import json,os,re,time,urllib.error,urllib.request,uuid
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,Protocol
try:
 from jsonschema import Draft202012Validator
except ImportError: Draft202012Validator=None
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'config/event-v0.3.schema.json').read_text(encoding='utf-8'))
class AdapterError(RuntimeError): pass
class Provider(Protocol):
 def complete_json(self,system_prompt:str,payload:Dict[str,Any])->Dict[str,Any]: ...
def now(): return datetime.now(timezone.utc).isoformat()
def new_id(p): return f'{p}_{uuid.uuid4()}'
try:
 from .safety import scan_danger, DANGER_REMINDER
except ImportError:
 from safety import scan_danger, DANGER_REMINDER
def danger(t): return scan_danger(t)['danger_detected']
def kind(t):
 if re.search(r'血压|血糖|体温|心率|\d{2,3}/\d{2,3}',t): return 'measurement'
 if re.search(r'药|处方|剂量|停药|加药|减药|服用',t): return 'medication'
 if re.search(r'头晕|咳嗽|走路|疼|痛|不舒服|发热|呼吸',t): return 'symptom'
 if re.search(r'医生|药师|建议|医嘱',t): return 'instruction'
 if '要不要' in t or '是否' in t:return 'question'
 return 'other'
class MockProvider:
 def complete_json(self,system_prompt,payload):
  t=str(payload.get('raw_text','')).strip(); rid=str(payload.get('record_id') or new_id('rec')); explicit=payload.get('source_kind'); src=explicit if explicit in ALLOWED_SOURCE_KINDS else 'unknown'
  if explicit not in ALLOWED_SOURCE_KINDS:
   if '转述' in t: src='family_report'
   elif '照护员' in t: src='caregiver'
   elif '老人' in t or '妈妈说' in t: src='elder'
   elif '女儿' in t or '儿子' in t or '家属' in t: src='family_observation'
   elif '处方' in t or '药盒' in t or 'OCR' in t or '出院单' in t: src='document'
  d=danger(t); rel=bool(re.search(r'今天|昨天|最近|大约|好像|不记得|不清楚|之前',t)); ek=kind(t)
  history=payload.get('history') or payload.get('history_events') or []
  refs=[]; conflict=False
  for h in history:
   if not isinstance(h,dict): continue
   hid=str(h.get('record_id') or h.get('id') or '')
   ht=str(h.get('raw_text') or h.get('text') or h.get('summary') or '')
   if not hid or not ht or ht == t: continue  # 精确同文保留为两条，不合并、不制造冲突
   hk=str(h.get('event_kind') or '')
   if hk and hk == ek or (ek == 'measurement' and re.search(r'血压|血糖|体温|心率|\d{2,3}/\d{2,3}',ht)):
    refs.append(hid); conflict=True
  if conflict: rel=True
  return {'schema_version':'event-v0.3','event_kind':ek,'summary':t[:500],'time':{'occurred':payload.get('occurred_time'),'recorded':payload.get('recorded_at') or now(),'certainty':'relative' if rel else ('unknown' if not payload.get('occurred_time') else 'exact')},'claims':[{'text':t[:500],'source_kind':src,'record_id':rid,'quote':t[:500]}],'review_required':True,'review_role':'emergency_services' if d else ('clinician_or_pharmacist' if ek in {'medication','instruction'} else 'family'),'escalation_level':'emergency' if d else 'none','conflict':{'present':conflict,'record_refs':refs},'provenance_preserved':True,'plan_change_allowed':False,'follow_up_questions':['请补充发生时间和可核验证据。'] if rel else [],'forbidden_actions':[]}
ALLOWED_SOURCE_KINDS={'elder','family_observation','family_report','caregiver','clinician_evidence','document','audio_transcript','system','unknown'}
@dataclass(frozen=True)
class Config:
 provider:str='mock'; base_url:str='https://api-inference.modelscope.cn/v1'; model:str=''; token:str=''; timeout:float=30
 @classmethod
 def from_env(cls):
  provider=os.getenv('MODEL_PROVIDER','mock').lower()
  if provider in {'deepseek','deepseek-ai'}:
   return cls(provider,os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com/v1').rstrip('/'),os.getenv('DEEPSEEK_MODEL','deepseek-chat'),os.getenv('DEEPSEEK_API_KEY',''),float(os.getenv('MODEL_TIMEOUT_SECONDS','30')))
  return cls(provider,os.getenv('MODELSCOPE_BASE_URL','https://api-inference.modelscope.cn/v1').rstrip('/'),os.getenv('MODELSCOPE_MODEL',''),os.getenv('MODELSCOPE_ACCESS_TOKEN',os.getenv('MODELSCOPE_TOKEN','')),float(os.getenv('MODEL_TIMEOUT_SECONDS','30')))
class ModelScopeProvider:
 def __init__(self,c):
  if not c.token: raise AdapterError('未配置 MODELSCOPE_ACCESS_TOKEN')
  if not c.model: raise AdapterError('未配置 MODELSCOPE_MODEL')
  self.c=c
 def complete_json(self,system_prompt,payload):
  body={'model':self.c.model,'temperature':0,'messages':[{'role':'system','content':system_prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]}
  req=urllib.request.Request(self.c.base_url+'/chat/completions',json.dumps(body,ensure_ascii=False).encode(),{'Authorization':'Bearer '+self.c.token,'Content-Type':'application/json'},method='POST')
  try:
   with urllib.request.urlopen(req,timeout=self.c.timeout) as r:data=json.loads(r.read().decode())
  except (urllib.error.URLError,TimeoutError,json.JSONDecodeError) as e: raise AdapterError(f'ModelScope 请求失败: {e}') from e
  try:
   c=data['choices'][0]['message']['content']; c=c if isinstance(c,str) else ''.join(x.get('text','') for x in c); return json.loads(re.sub(r'^```json\s*|\s*```$','',c.strip()))
  except (KeyError,IndexError,TypeError,json.JSONDecodeError) as e: raise AdapterError(f'模型返回不是 JSON: {e}') from e
class DeepSeekProvider:
 def __init__(self,c):
  if not c.token: raise AdapterError('未配置 DEEPSEEK_API_KEY')
  if not c.model: raise AdapterError('未配置 DEEPSEEK_MODEL')
  self.c=c
 def complete_json(self,system_prompt,payload):
  body={'model':self.c.model,'temperature':0,'messages':[{'role':'system','content':system_prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}], 'response_format':{'type':'json_object'}}
  req=urllib.request.Request(self.c.base_url+'/chat/completions',json.dumps(body,ensure_ascii=False).encode(),{'Authorization':'Bearer '+self.c.token,'Content-Type':'application/json'},method='POST')
  try:
   with urllib.request.urlopen(req,timeout=self.c.timeout) as r:data=json.loads(r.read().decode())
  except (urllib.error.URLError,TimeoutError,json.JSONDecodeError) as e: raise AdapterError(f'DeepSeek 请求失败: {e}') from e
  try:
   c=data['choices'][0]['message']['content']; c=c if isinstance(c,str) else ''.join(x.get('text','') for x in c); return json.loads(re.sub(r'^```json\s*|\s*```$','',c.strip()))
  except (KeyError,IndexError,TypeError,json.JSONDecodeError) as e: raise AdapterError(f'DeepSeek 返回不是 JSON: {e}') from e
SYSTEM_PROMPT=(ROOT/'prompts/01-系统提示词.md').read_text(encoding='utf-8') if (ROOT/'prompts/01-系统提示词.md').exists() else '只整理可追溯事实，不诊断，不改药。'
TASK_PROMPT=(ROOT/'prompts/02-事件整理任务提示词.md').read_text(encoding='utf-8') if (ROOT/'prompts/02-事件整理任务提示词.md').exists() else ''
SCHEMA_TEXT=json.dumps(SCHEMA,ensure_ascii=False,separators=(',',':'))
def build_prompt():
 return SYSTEM_PROMPT+'\n\n'+TASK_PROMPT+'\n\n输出必须严格符合以下 JSON Schema：\n'+SCHEMA_TEXT
def _history_records(payload):
 hs=payload.get('history') or payload.get('history_events') or []
 return hs if isinstance(hs,list) else []
def _allowed_record_ids(payload):
 ids={str(payload.get('record_id'))} if payload.get('record_id') else set()
 for h in _history_records(payload):
  if isinstance(h,dict) and (h.get('record_id') or h.get('id')): ids.add(str(h.get('record_id') or h.get('id')))
 return ids
def _source_texts(payload):
 texts=[str(payload.get('raw_text',''))]
 for h in _history_records(payload):
  if isinstance(h,dict): texts += [str(h.get(k,'')) for k in ('raw_text','text','summary','quote') if h.get(k)]
 return texts
def validate_output(out,raw,payload=None):
 payload=payload or {'raw_text':raw}
 if Draft202012Validator is None: raise AdapterError('缺少 jsonschema 依赖，拒绝接受模型输出；请先安装并固定版本。')
 es=sorted(Draft202012Validator(SCHEMA).iter_errors(out),key=lambda e:list(e.path))
 if es: raise AdapterError('Schema 校验失败: '+es[0].message)
 if out.get('provenance_preserved') is not True or out.get('plan_change_allowed') is not False: raise AdapterError('安全字段不满足硬规则')
 # 允许用户原文出现在 quote 中；只拦截模型生成的摘要、追问等字段，避免把用户说的“诊断/停药”误判成模型建议。
 generated=[out.get('summary','')]+list(out.get('follow_up_questions') or [])
 for claim in out.get('claims') or []:
  text=claim.get('text',''); quote=claim.get('quote')
  if text and text != quote: generated.append(text)
 if re.search(r'诊断为|确诊为|建议停药|建议加药|建议减药|调整剂量为|替代医生',json.dumps(generated,ensure_ascii=False)): raise AdapterError('模型输出触发越权拦截')
 allowed_ids=_allowed_record_ids(payload)
 source_texts=_source_texts(payload)
 for claim in out.get('claims') or []:
  if claim.get('record_id') not in allowed_ids: raise AdapterError('claim.record_id 不属于当前记录或后端历史。')
  quote=claim.get('quote')
  if quote is not None and str(quote) not in source_texts: raise AdapterError('claim.quote 不对应当前输入或后端历史证据。')
 # 时间是高风险字段：发生时间只能沿用后端传入值，或逐字出现在输入/历史证据中；记录时间由服务端控制。
 occurred=out.get('time',{}).get('occurred'); supplied=payload.get('occurred_time')
 if occurred is not None and supplied is None and not any(str(occurred) in text for text in source_texts):
  raise AdapterError('time.occurred 没有输入证据支持，禁止凭空填写。')
 if supplied is not None and occurred not in {supplied,str(supplied)}:
  raise AdapterError('time.occurred 必须沿用后端提供的 occurred_time。')
 recorded=out.get('time',{}).get('recorded'); server_recorded=payload.get('recorded_at')
 if server_recorded and recorded != server_recorded:
  raise AdapterError('time.recorded 必须使用后端 recorded_at。')
 if danger(raw) and (out.get('escalation_level')!='emergency' or out.get('review_role')!='emergency_services'): raise AdapterError('危险输入必须升级为 emergency_services')
 if out.get('review_required') is not True: raise AdapterError('医疗交接输出必须 review_required=true')
 if out.get('event_kind') in {'medication','instruction'} and out.get('review_role')!='clinician_or_pharmacist' and out.get('escalation_level')!='emergency': raise AdapterError('用药/医嘱事件必须交由 clinician_or_pharmacist 复核')
 return out
def apply_safety_guard(out,raw):
 if not isinstance(out,dict): raise AdapterError('模型输出必须为 JSON 对象')
 if not danger(raw): return out,False
 fixed=dict(out)
 fixed['escalation_level']='emergency'; fixed['review_role']='emergency_services'; fixed['review_required']=True; fixed['plan_change_allowed']=False
 qs=out.get('follow_up_questions',[])
 if not isinstance(qs,list): raise AdapterError('follow_up_questions 必须为数组')
 fixed['follow_up_questions']=[DANGER_REMINDER]+[q for q in qs if q!=DANGER_REMINDER][:4]
 return fixed,fixed!=out
def provider_from(c=None):
 c=c or Config.from_env()
 if c.provider=='mock':return MockProvider()
 if c.provider in {'modelscope','魔搭'}:return ModelScopeProvider(c)
 if c.provider in {'deepseek','deepseek-ai'}:return DeepSeekProvider(c)
 raise AdapterError('不支持的 MODEL_PROVIDER')
def organize_event(payload,provider=None):
 if not isinstance(payload,dict) or not str(payload.get('raw_text','')).strip():raise AdapterError('raw_text 不能为空')
 raw=str(payload['raw_text']); safety=scan_danger(raw)  # Always before provider selection/network.
 start=time.perf_counter(); p=provider or provider_from()
 model_out=p.complete_json(build_prompt(),payload)
 out,guard=apply_safety_guard(model_out,raw); out=validate_output(out,raw,payload)
 return {'ok':True,'ai_failed':False,'trace_id':new_id('tr'),'provider':type(p).__name__,'prompt_version':'prompt-v0.4','schema_version':'event-v0.3','latency_ms':round((time.perf_counter()-start)*1000,2),'safety_guard_applied':guard,'output':out,'local_safety':safety,**safety}
