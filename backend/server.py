from __future__ import annotations
import json, os, secrets, mimetypes, hashlib
from urllib.error import URLError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote
from pathlib import Path
try:
 from .adapter import AdapterError, Config, organize_event, PROMPT_VERSION, SCHEMA_VERSION, PROMPT_SHA256, payload_sha256
 from .store import SQLiteStore, StoreError, Unauthorized, Forbidden
except ImportError:
 from adapter import AdapterError, Config, organize_event, PROMPT_VERSION, SCHEMA_VERSION, PROMPT_SHA256, payload_sha256
 from store import SQLiteStore, StoreError, Unauthorized, Forbidden
ROOT=Path(__file__).resolve().parents[1]; STATIC=(ROOT/'frontend'/'dist').resolve(); SESSION_TOKEN=secrets.token_urlsafe(24)
DB_PATH=os.getenv('DB_PATH',os.getenv('API_DB_PATH',str(ROOT/'runtime'/'records.sqlite3'))); STORE=SQLiteStore(DB_PATH)
ALLOWED_ORIGIN=os.getenv('ALLOWED_ORIGIN','')
def model_evidence(event):
 # Only original evidence crosses the model boundary. Prior drafts, audit
 # notes, review state and model output must never become new source facts.
 return {key:event.get(key) for key in ('record_id','raw_text','source_kind','recorded_at','occurred_time')}

def configured_model_metadata():
 try:
  config=Config.from_env()
  return {'provider':config.provider,'model_id':'mock-v1' if config.provider=='mock' else config.model or None}
 except (ValueError,TypeError):
  return {'provider':None,'model_id':None}

def model_failure_details(error):
 # Use known codes, never a remote message/body, URL or arbitrary error field.
 messages={'model_timeout':'模型超时','model_network_error':'网络连接失败',
           'model_configuration_invalid':'模型配置无效','model_redirect_rejected':'模型地址返回重定向，已拒绝转发',
           'model_response_too_large':'模型响应超过大小限制','model_output_truncated':'模型输出被截断',
           'model_response_invalid':'模型返回内容格式无效','model_http_error':'模型服务请求失败',
           'model_account_binding_required':'魔搭账号需先绑定阿里云账号'}
 code=error.code if isinstance(error,AdapterError) and type(error.code) is str and error.code in messages else None
 status=error.status if isinstance(error,AdapterError) and code in {'model_http_error','model_account_binding_required'} and type(error.status)==int and 100<=error.status<=599 else None
 if code:
  reason=messages[code]
  if code=='model_http_error' and status in (401,403): reason='模型服务鉴权或访问权限失败'
  elif code=='model_http_error' and status==429: reason='模型服务限流或额度不足'
  return {'failure_reason':reason,'failure_code':code,**({'provider_http_status':status} if status is not None else {})}
 cause=error.__cause__ or error
 reason=('模型超时' if isinstance(cause,TimeoutError) else '模型返回非法 JSON' if isinstance(cause,json.JSONDecodeError) else '网络连接失败' if isinstance(cause,URLError) else '模型调用失败或返回内容未通过校验')
 return {'failure_reason':reason}

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def end_headers(self):
  o=self.headers.get('Origin',''); expected=ALLOWED_ORIGIN or ('http://'+self.headers.get('Host',''))
  if o and o==expected:self.send_header('Access-Control-Allow-Origin',o);self.send_header('Vary','Origin')
  self.send_header('Cache-Control','no-store');super().end_headers()
 def send_json(self,code,p):
  b=json.dumps(p,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def body(self):
  n=int(self.headers.get('Content-Length','0'))
  if n>1_000_000: raise StoreError('body_too_large')
  x=json.loads(self.rfile.read(n).decode() or '{}')
  if not isinstance(x,dict): raise StoreError('body_must_object')
  return x
 def csrf(self):
  if self.command=='GET': return True
  if urlparse(self.path).path in ('/api/auth/households','/api/auth/login'): return True
  # New account sessions use X-Auth-Token; retain legacy local token for v4 UI.
  if self.headers.get('X-Auth-Token'): return True
  if self.headers.get('X-Session-Token')!=SESSION_TOKEN:return False
  o=self.headers.get('Origin',''); expected=ALLOWED_ORIGIN or ('http://'+self.headers.get('Host',''))
  return not o or o==expected
 def _auth_ctx(self, permission=None, household_id=None):
  token=self.headers.get('X-Auth-Token')
  if not token:return None
  try:return STORE.authorize(token, permission, household_id) if permission else STORE.authenticate(token)
  except StoreError: return None
 def do_OPTIONS(self): self.send_response(204);self.send_header('Access-Control-Allow-Headers','Content-Type, Idempotency-Key, X-Session-Token, X-Auth-Token');self.end_headers()
 def do_GET(self):
  p=unquote(urlparse(self.path).path)
  if p=='/health':
   c=Config.from_env();return self.send_json(200,{'ok':True,'service':'medical-handoff-p0','provider':c.provider,'storage':'sqlite','mode':'local_single_household','schema_version':SCHEMA_VERSION,'session_token':SESSION_TOKEN})
  if p=='/api/events':
   ctx=self._auth_ctx()
   if self.headers.get('X-Auth-Token') and ctx is None:
    return self.send_json(401,{'ok':False,'error':'invalid_session'})
   return self.send_json(200,{'ok':True,'events':STORE.list(ctx['household_id'] if ctx else None)})
  if p=='/api/auth/me':
   try:return self.send_json(200,{'ok':True,'user':STORE.authenticate(self.headers.get('X-Auth-Token'))})
   except StoreError as e:return self.send_json(e.status,{'ok':False,'error':str(e)})
  if p=='/api/auth/members':
   try:
    ctx=STORE.authorize(self.headers.get('X-Auth-Token'),'read'); return self.send_json(200,{'ok':True,'members':STORE.list_members(ctx['household_id'])})
   except StoreError as e:return self.send_json(e.status,{'ok':False,'error':str(e)})
  if p.startswith('/api/events/'):
   z=p.strip('/').split('/');rid=z[2] if len(z)>2 else ''
   try:
    if len(z)==4 and z[3]=='history':
     ctx=self._auth_ctx()
     if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
     if ctx and not STORE.get(rid,ctx['household_id']): return self.send_json(404,{'ok':False,'error':'event_not_found'})
     h,a=STORE.history(rid);return self.send_json(200,{'ok':True,'history':h,'audit':a})
    if len(z)==3:
     ctx=self._auth_ctx()
     if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
     e=STORE.get(rid,ctx['household_id'] if ctx else None);return self.send_json(200,{'ok':True,'event':e}) if e else self.send_json(404,{'ok':False,'error':'event_not_found'})
   except StoreError as e:return self.send_json(e.status,{'ok':False,'error':str(e)})
  if p.startswith('/api/handoffs/'):
   try:
    ctx=self._auth_ctx()
    if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
    handoff=STORE.get_handoff(p.split('/')[-1])
    if ctx and handoff.get('household_id') not in (None,ctx['household_id']):return self.send_json(404,{'ok':False,'error':'handoff_not_found'})
    return self.send_json(200,{'ok':True,'handoff':handoff})
   except StoreError as e:return self.send_json(e.status,{'ok':False,'error':str(e)})
  # Frontend owner may place a build under frontend/dist, or use a dev proxy.
  if not p.startswith('/api/'):
   f=(STATIC/('index.html' if p=='/' else p.lstrip('/'))).resolve()
   if STATIC in f.parents and f.suffix.lower() in {'.html','.js','.css','.json','.svg','.png','.jpg','.ico','.woff2'} and f.is_file():
    b=f.read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(f))[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
  return self.send_json(404,{'ok':False,'error':'not_found'})
 def do_POST(self):
  if not self.csrf():return self.send_json(403,{'ok':False,'error':'csrf_or_origin_rejected'})
  p=urlparse(self.path).path
  try:b=self.body()
  except Exception as e:return self.send_json(400,{'ok':False,'error':str(e)})
  actor=str(b.get('actor_name') or '本地用户')
  try:
   if p=='/api/auth/households':
    result=STORE.create_household(b.get('name'),b.get('display_name'),b.get('role','owner'),b.get('external_key'),b.get('password'))
    login=STORE.login(user_id=result['user_id'],household_id=result['household_id'],password=b.get('password'))
    return self.send_json(201,{'ok':True,'household':result,'session':login})
   if p=='/api/auth/login':
    return self.send_json(200,{'ok':True,'session':STORE.login(b.get('user_id'),b.get('display_name'),b.get('household_id'),password=b.get('password'))})
   if p=='/api/auth/logout':
    token=self.headers.get('X-Auth-Token'); STORE.revoke_session(token); return self.send_json(200,{'ok':True})
   if p=='/api/auth/members':
    ctx=STORE.authorize(self.headers.get('X-Auth-Token'),'manage_members',b.get('household_id'))
    m=STORE.add_member(ctx['household_id'],b.get('display_name'),b.get('role','family'),b.get('external_key'),b.get('password'))
    return self.send_json(201,{'ok':True,'member':m})
   if p=='/api/events':
    for k in ('raw_text','source_kind','actor_name'):
     if not isinstance(b.get(k),str) or not b[k].strip():raise StoreError(k+'_required')
    if len(b['raw_text'])>10000:raise StoreError('raw_text_too_long')
    key=self.headers.get('Idempotency-Key')
    if not key:raise StoreError('idempotency_key_required')
    ctx=self._auth_ctx('create')
    if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
    e,created=STORE.create(b,key,actor,ctx['household_id'] if ctx else 'hh_local_default');return self.send_json(201 if created else 200,{'ok':True,'created':created,'event':e})
   if p=='/api/handoffs':
    ctx=self._auth_ctx('read')
    if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
    return self.send_json(201,{'ok':True,'handoff':STORE.handoff(ctx['household_id'] if ctx else None)})
   z=p.strip('/').split('/')
   if len(z)>=4 and z[:2]==['api','events']:
    ctx=self._auth_ctx();
    if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
    rid=z[2];e=STORE.get(rid,ctx['household_id'] if ctx else None)
    if not e:raise StoreError('event_not_found')
    if z[3]=='organize':
     if ctx: STORE.authorize(self.headers.get('X-Auth-Token'),'organize',ctx['household_id'])
     expected=b.get('expected_version',e['version']); related=[STORE.get(x) for x in e.get('related_record_ids',[])]; payload={**model_evidence(e),'history':[model_evidence(item) for item in related]}
     safety=e['local_safety']
     try:
      r=organize_event(payload)
     except Exception as ex:
      # Do not expose provider bodies/credentials or misclassify storage/version
      # failures: only the provider+validation call is caught here.
      cause=ex.__cause__ or ex
      failure={'error':'ai_organize_failed','failure_type':type(ex).__name__,'failure_cause_type':type(cause).__name__,'trace_id':'tr_'+secrets.token_hex(16),'raw_text_sha256':hashlib.sha256(e['raw_text'].encode()).hexdigest(),'input_sha256':payload_sha256(payload),'prompt_version':PROMPT_VERSION,'prompt_sha256':PROMPT_SHA256,'schema_version':SCHEMA_VERSION,'raw_text_preserved':True,'local_safety':safety,**configured_model_metadata(),**model_failure_details(ex)}
      STORE.fail(rid,'organize_failed',actor,failure)
      return self.send_json(422,{'ok':False,'ai_failed':True,'record_id':rid,'event':STORE.get(rid),'local_safety':safety,**failure,**safety})
     # The outward notice includes historical positives retained on rule upgrade.
     r.update(local_safety=safety,**safety)
     out=STORE.organize(rid,expected,r,actor)
     return self.send_json(200,{'event':out,'raw_text_preserved':True,**r})
    if z[3]=='review':
     if ctx: STORE.authorize(self.headers.get('X-Auth-Token'),'review',ctx['household_id'])
     return self.send_json(200,{'ok':True,'event':STORE.review(rid,b.get('expected_version'),b.get('action'),actor,b.get('note'))})
    if z[3]=='revise':
     if ctx: STORE.authorize(self.headers.get('X-Auth-Token'),'revise',ctx['household_id'])
     return self.send_json(201,{'ok':True,'event':STORE.revise(rid,b.get('expected_version'),b,actor)})
  except StoreError as e:return self.send_json(e.status,{'ok':False,'error':str(e)})
  except Exception as e:return self.send_json(500,{'ok':False,'error':str(e)})
  return self.send_json(404,{'ok':False,'error':'not_found'})
def serve(host='127.0.0.1',port=None): ThreadingHTTPServer((host,int(os.getenv('API_PORT',port or 18768))),Handler).serve_forever()
if __name__=='__main__':serve()
