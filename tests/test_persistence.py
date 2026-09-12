import os, tempfile, threading
from backend.store import SQLiteStore, Conflict, StoreError

def draft(recorded=None, kind='symptom', escalation='none', conflict=False, review_role='family'):
 return {'output': {'schema_version':'event-v0.3','event_kind':kind,'summary':'记录','time':{'occurred':None,'recorded':recorded,'certainty':'relative'},'claims':[],'review_required':True,'review_role':review_role,'escalation_level':escalation,'conflict':{'present':conflict,'record_refs':[]},'provenance_preserved':True,'plan_change_allowed':False,'follow_up_questions':[],'forbidden_actions':[]},'trace_id':'t','provider':'MockProvider','prompt_version':'p','schema_version':'s','latency_ms':1}
def payload(text='女儿观察：今天头晕', actor='女儿'):
 return {'raw_text':text,'source_kind':'family_observation','actor_name':actor}
def test_persistence_and_state_machine():
 with tempfile.TemporaryDirectory() as d:
  path=os.path.join(d,'家庭记录.sqlite3'); s=SQLiteStore(path); e,created=s.create(payload(),'k1'); assert created and e['state']=='inbox'
  assert s.create(payload(),'k1')[1] is False
  try:s.create({**payload(),'raw_text':'changed'},'k1'); raise AssertionError
  except Conflict: pass
  for bad in (None, True, 0, '1'):
   try:s.organize(e['record_id'],bad,draft(),'x'); raise AssertionError
   except StoreError: pass
  try:s.review(e['record_id'],1,'confirm','儿子',''); raise AssertionError
  except Conflict: pass
  e=s.organize(e['record_id'],1,draft(e['recorded_at']),'system'); assert e['state']=='draft' and e['version']==2
  e=s.review(e['record_id'],2,'confirm','儿子','确认记录准确'); assert e['state']=='recorded' and e['version']==3
  try:s.organize(e['record_id'],3,draft(),'system'); raise AssertionError
  except Conflict: pass
  try:s.review(e['record_id'],3,'confirm','女儿','重复确认'); raise AssertionError
  except Conflict: pass
  old_raw=e['raw_text']; new=s.revise(e['record_id'],3,{**payload('修订：今天没有头晕'),'reason':'家属更正'},'女儿'); assert new['supersedes_id']==e['record_id']
  old=s.get(e['record_id']); assert old['state']=='superseded' and old['raw_text']==old_raw and old['version']==4
  try:s.revise(e['record_id'],4,{**payload(),'reason':'再次修订'},'女儿'); raise AssertionError
  except Conflict: pass
  try:s.revise(new['record_id'],1,{**payload(),'reason':''},'女儿'); raise AssertionError
  except StoreError: pass
  h=s.handoff(); assert all(x['state']!='superseded' for x in h['items']); assert h['unresolved_count']>=1
  snap=h['items'][0]; assert s.get_handoff(h['handoff_id'])['items']==h['items']
  s2=SQLiteStore(path); assert s2.get(e['record_id'])['raw_text']==old_raw; assert len(s2.history(e['record_id'])[0])>=4
  # Same optimistic version: at most one thread can transition.
  x,_=s2.create(payload('并发测试'),'parallel'); results=[]
  def worker():
   try: results.append(('ok',s2.organize(x['record_id'],1,draft(),'x')['version']))
   except Exception as ex: results.append((type(ex).__name__,str(ex)))
  ts=[threading.Thread(target=worker) for _ in range(2)]
  [t.start() for t in ts]; [t.join() for t in ts]
  assert sum(r[0]=='ok' for r in results)==1, results
  assert sum(r[0]=='Conflict' for r in results)==1, results
  # Clinical risk is still unresolved after family confirmation.
  risk,_=s2.create(payload('老人胸痛'),'risk'); r=s2.organize(risk['record_id'],1,draft(risk['recorded_at'],escalation='emergency',review_role='emergency_services'),'system'); r=s2.review(r['record_id'],2,'confirm','家属','确认记录准确'); hh=s2.handoff(); item=next(i for i in hh['items'] if i['record_id']==r['record_id']); assert item['unresolved'] and 'escalation_not_cleared' in item['unresolved_reasons']
 print('PERSISTENCE_TEST_PASS state_machine=1 immutable=1 restart=1 concurrency=1 handoff=1')
if __name__=='__main__': test_persistence_and_state_machine()
