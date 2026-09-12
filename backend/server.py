from __future__ import annotations
import json, os, secrets, mimetypes, hashlib, re
from email.parser import BytesParser
from email.policy import default as email_policy
from dataclasses import asdict, is_dataclass
from urllib.error import URLError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote
from pathlib import Path
try:
 from .adapter import Config, organize_event
 from .media_backend import create_default_media_backend
 from .media_store import MediaStoreError
 from .store import SQLiteStore, StoreError, NotFound, Conflict, expected_version
except ImportError:
 from adapter import Config, organize_event
 from media_backend import create_default_media_backend
 from media_store import MediaStoreError
 from store import SQLiteStore, StoreError, NotFound, Conflict, expected_version
ROOT=Path(__file__).resolve().parents[1]; STATIC=(ROOT/'frontend'/'dist').resolve(); SESSION_TOKEN=secrets.token_urlsafe(24)
DB_PATH=os.getenv('DB_PATH',os.getenv('API_DB_PATH',str(ROOT/'runtime'/'records.sqlite3'))); STORE=SQLiteStore(DB_PATH)
ALLOWED_ORIGIN=os.getenv('ALLOWED_ORIGIN','')
MAX_MEDIA_REQUEST_BYTES=int(os.getenv('MEDIA_REQUEST_MAX_BYTES','0') or '0')
MEDIA_ROOT=os.getenv('MEDIA_ROOT',str(ROOT/'runtime'/'media'))
MEDIA_BACKEND=create_default_media_backend(STORE,root=MEDIA_ROOT)

_SAFE_MEDIA_ID=re.compile(r'^(?:media|upload)_[A-Za-z0-9_-]+$')

def _public_value(value):
 if is_dataclass(value):return asdict(value)
 if isinstance(value,dict):return {k:_public_value(v) for k,v in value.items() if 'path' not in k.lower()}
 if isinstance(value,(list,tuple)):return [_public_value(v) for v in value]
 return value

def _safe_media_id(value,prefix):
 return isinstance(value,str) and value.startswith(prefix+'_') and _SAFE_MEDIA_ID.fullmatch(value) is not None

def _media_error_status(error):
 code=getattr(error,'code',str(error))
 if code in {'limit_exceeded','request_too_large'}:return 413
 if code=='media_limits_not_configured':return 503
 if code in {'invalid_media','integrity_mismatch'}:return 422
 if code in {'storage_failed','storage_corrupt','unsafe_storage'}:return 500
 if code in {'unsupported_format','content_type_kind_mismatch'}:return 415
 if code in {'media_not_found','upload_not_found'}:return 404
 if code in {'idempotency_key_payload_mismatch','upload_conflict','upload_incomplete','upload_completed','stale_version'}:return 409
 return getattr(error,'status',400)

def _media_error_code(error):
 code=getattr(error,'code',str(error))
 known={
  'limit_exceeded','request_too_large','unsupported_format','content_type_kind_mismatch',
  'media_not_found','upload_not_found','idempotency_key_payload_mismatch','upload_conflict',
  'upload_incomplete','upload_completed','stale_version','idempotency_key_required',
  'invalid_media','invalid_upload','invalid_part','integrity_mismatch','provider_timeout',
  'provider_unavailable','provider_not_configured','provider_auth_failed',
  'provider_rate_limited','invalid_provider_response','no_text_detected','storage_failed',
  'storage_corrupt','unsafe_storage','media_limits_not_configured','invalid_range',
 }
 return code if code in known else 'media_request_failed'

def _positive_env(name):
 value=os.getenv(name)
 return int(value) if value and value.isdigit() and int(value)>0 else None

def _media_capabilities():
 enabled=all(_positive_env(name) is not None for name in (
   'MEDIA_UPLOAD_MAX_BYTES','MEDIA_UPLOAD_PART_MAX_BYTES','MEDIA_UPLOAD_MAX_PARTS',
  ))
 return {
  'enabled': enabled,
  'disabled_reason': None if enabled else 'media_limits_not_configured',
  'max_total_bytes': _positive_env('MEDIA_UPLOAD_MAX_BYTES'),
  'max_part_bytes': _positive_env('MEDIA_UPLOAD_PART_MAX_BYTES'),
  'max_parts': _positive_env('MEDIA_UPLOAD_MAX_PARTS'),
  'max_audio_duration_seconds': None,
  'max_image_pixels': None,
  'audio_content_types': ['audio/aac','audio/flac','audio/m4a','audio/mp3','audio/mpeg','audio/mp4','audio/ogg','audio/wav','audio/webm','audio/x-m4a','audio/x-wav'],
  'image_content_types': ['image/gif','image/jpeg','image/png','image/tiff','image/webp'],
  'multipart_upload': True,
  'resumable_parts': True,
 }

def _media_limits():
 limits=_media_capabilities()
 if not limits['enabled']:
  limits['disabled_reason']='media_limits_not_configured'
 return limits
def request_actor(b):
 if 'actor_name' not in b:return '本地用户'
 actor=b['actor_name']
 if not isinstance(actor,str) or not actor.strip():raise StoreError('actor_name_required')
 if len(actor)>80:raise StoreError('actor_name_too_long')
 return actor
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def end_headers(self):
  o=self.headers.get('Origin',''); expected=ALLOWED_ORIGIN or ('http://'+self.headers.get('Host',''))
  if o and o==expected:self.send_header('Access-Control-Allow-Origin',o);self.send_header('Vary','Origin')
  self.send_header('Cache-Control','no-store');super().end_headers()
 def send_json(self,code,p):
  b=json.dumps(p,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def send_bytes(self,code,payload,content_type,extra_headers=None):
  self.send_response(code);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(payload)))
  for name,value in (extra_headers or {}).items():self.send_header(name,value)
  self.end_headers();self.wfile.write(payload)
 def body(self):
  n=int(self.headers.get('Content-Length','0'))
  if n>1_000_000: raise StoreError('body_too_large')
  x=json.loads(self.rfile.read(n).decode() or '{}')
  if not isinstance(x,dict): raise StoreError('body_must_object')
  return x
 def media_body(self):
  try:n=int(self.headers.get('Content-Length',''))
  except ValueError:raise StoreError('invalid_content_length') from None
  if n<1:raise StoreError('body_required')
  request_limit = MAX_MEDIA_REQUEST_BYTES or _media_limits().get('max_total_bytes')
  if request_limit is not None and n>request_limit:
   e=StoreError('request_too_large');e.status=413;raise e
  content_type=self.headers.get('Content-Type','')
  if not content_type.lower().startswith('multipart/form-data;'):
   e=StoreError('unsupported_format');e.status=415;raise e
  raw=self.rfile.read(n)
  if len(raw)!=n:raise StoreError('incomplete_request_body')
  try:
   message=BytesParser(policy=email_policy).parsebytes(
    b'Content-Type: '+content_type.encode('ascii')+b'\r\nMIME-Version: 1.0\r\n\r\n'+raw
   )
  except (UnicodeEncodeError,ValueError):raise StoreError('invalid_multipart_payload') from None
  if not message.is_multipart():raise StoreError('invalid_multipart_payload')
  fields={};files={}
  for part in message.iter_parts():
   name=part.get_param('name',header='content-disposition')
   if not name or name in fields or name in files:raise StoreError('invalid_multipart_payload')
   payload=part.get_payload(decode=True)
   if not isinstance(payload,bytes):raise StoreError('invalid_multipart_payload')
   filename=part.get_filename()
   if filename is None:
    try:fields[name]=payload.decode('utf-8')
    except UnicodeDecodeError:raise StoreError('invalid_multipart_payload') from None
   else:files[name]={'filename':filename,'content_type':part.get_content_type(),'data':payload}
  return fields,files
 def media_backend(self):
  if MEDIA_BACKEND is None:raise StoreError('media_backend_unavailable')
  return MEDIA_BACKEND
 def media_write_enabled(self):
  if not _media_limits()['enabled']:
   error=StoreError('media_limits_not_configured');error.status=503;raise error
 def media_read_allowed(self):
  auth_token=self.headers.get('X-Auth-Token')
  if auth_token:return self._auth_ctx() is not None
  return self.headers.get('X-Session-Token')==SESSION_TOKEN
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
 def do_OPTIONS(self): self.send_response(204);self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type, Idempotency-Key, X-Session-Token, X-Auth-Token, Range');self.end_headers()
 def do_GET(self):
  try:return self._do_GET()
  except StoreError as e:return self.send_json(e.status,{'ok':False,'error':str(e)})
  except MediaStoreError as e:return self.send_json(_media_error_status(e),{'ok':False,'error':_media_error_code(e)})
  except Exception:return self.send_json(500,{'ok':False,'error':'internal_server_error'})
 def _do_GET(self):
  p=unquote(urlparse(self.path).path)
  if p=='/api/media/capabilities':
   return self.send_json(200,{'ok':True,'capabilities':_media_capabilities()})
  if p=='/health':
   c=Config.from_env();return self.send_json(200,{'ok':True,'service':'medical-handoff-p0','provider':c.provider,'storage':'sqlite','mode':'local_single_household','schema_version':'event-v0.3','session_token':SESSION_TOKEN})
  if p=='/api/events':
   ctx=self._auth_ctx()
   if self.headers.get('X-Auth-Token') and ctx is None:
    return self.send_json(401,{'ok':False,'error':'invalid_session'})
   return self.send_json(200,{'ok':True,'events':STORE.list(ctx['household_id'] if ctx else None)})
  if p=='/api/media' or p.startswith('/api/media/'):
   if not self.media_read_allowed():return self.send_json(403,{'ok':False,'error':'csrf_or_origin_rejected'})
   backend=self.media_backend();ctx=self._auth_ctx();household_id=ctx['household_id'] if ctx else None
   if p=='/api/media':return self.send_json(200,{'ok':True,'media':_public_value(backend.list_media(household_id))})
   parts=p.strip('/').split('/')
   if len(parts) not in {3,4} or parts[:2]!=['api','media'] or not _safe_media_id(parts[2],'media'):
    return self.send_json(404,{'ok':False,'error':'not_found'})
   media_id=parts[2]
   media=backend.get_media(media_id,household_id)
   if not media:raise NotFound('media_not_found')
   if len(parts)==3:return self.send_json(200,{'ok':True,'media':_public_value(media)})
   if parts[3]!='original':return self.send_json(404,{'ok':False,'error':'not_found'})
   with backend.open_original(media_id,household_id) as original:
    payload=original.read()
   content_type=_public_value(media).get('content_type') or 'application/octet-stream'
   total=len(payload);headers={'Accept-Ranges':'bytes'};range_header=self.headers.get('Range')
   if range_header:
    match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header.strip())
    if not match or (not match.group(1) and not match.group(2)):return self.send_json(416,{'ok':False,'error':'invalid_range'})
    if match.group(1):
     start=int(match.group(1));end=int(match.group(2)) if match.group(2) else total-1
    else:
     length=int(match.group(2));start=max(0,total-length);end=total-1
    if start>=total or end<start:return self.send_json(416,{'ok':False,'error':'invalid_range'})
    end=min(end,total-1);headers['Content-Range']=f'bytes {start}-{end}/{total}'
    return self.send_bytes(206,payload[start:end+1],content_type,headers)
   return self.send_bytes(200,payload,content_type,headers)
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
  if p.startswith('/api/media/') and not p.startswith('/api/media/uploads'):
   try:self.media_write_enabled()
   except StoreError as e:return self.send_json(e.status,{'ok':False,'error':str(e)})
  if p=='/api/media/uploads' or p.startswith('/api/media/uploads/'):
   try:return self._do_media_upload_POST(p)
   except Exception as e:
    if isinstance(e,StoreError) or hasattr(e,'code'):
     return self.send_json(_media_error_status(e),{'ok':False,'error':_media_error_code(e)})
    return self.send_json(500,{'ok':False,'error':'internal_server_error'})
  try:b=self.body()
  except StoreError as e:return self.send_json(e.status,{'ok':False,'error':str(e)})
  except (json.JSONDecodeError,UnicodeDecodeError,ValueError):return self.send_json(400,{'ok':False,'error':'invalid_json_payload'})
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
    actor=request_actor(b)
    for k in ('raw_text','source_kind','actor_name'):
     if not isinstance(b.get(k),str) or not b[k].strip():raise StoreError(k+'_required')
    if len(b['raw_text'])>10000:raise StoreError('raw_text_too_long')
    key=self.headers.get('Idempotency-Key')
    if not key:raise StoreError('idempotency_key_required')
    ctx=self._auth_ctx('create')
    if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
    e,created=STORE.create(b,key,actor,ctx['household_id'] if ctx else 'hh_local_default');return self.send_json(201 if created else 200,{'ok':True,'created':created,'event':e})
   if p=='/api/handoffs':
    if b:raise StoreError('handoff_body_must_be_empty_object')
    ctx=self._auth_ctx('read')
    if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
    return self.send_json(201,{'ok':True,'handoff':STORE.handoff(ctx['household_id'] if ctx else None)})
   z=p.strip('/').split('/')
   if len(z)==4 and z[:2]==['api','media'] and z[3]=='recognize':
    self.media_write_enabled()
    if not _safe_media_id(z[2],'media'):return self.send_json(404,{'ok':False,'error':'not_found'})
    key=self.headers.get('Idempotency-Key')
    if not key:raise StoreError('idempotency_key_required')
    ctx=self._auth_ctx('create')
    if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
    result=self.media_backend().start_recognition(
     z[2],b.get('expected_version'),key,
     actor=request_actor(b),household_id=ctx['household_id'] if ctx else None,
    )
    action = result.get('action')
    status = 200 if action in {'existing', 'resume_link'} and result.get('media', {}).get('recognition_status') == 'succeeded' else 202
    return self.send_json(status,{'ok':True,**_public_value(result)})
   if len(z)==4 and z[:2]==['api','media'] and z[3]=='link':
    self.media_write_enabled()
    if not _safe_media_id(z[2],'media'):return self.send_json(404,{'ok':False,'error':'not_found'})
    key=self.headers.get('Idempotency-Key')
    if not key:raise StoreError('idempotency_key_required')
    ctx=self._auth_ctx('create')
    if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
    expected=expected_version(b.get('expected_version'))
    result=self.media_backend().link_media(
     z[2],key,expected,actor=request_actor(b),household_id=ctx['household_id'] if ctx else None,
    )
    return self.send_json(201 if result.get('event_created') else 200,{'ok':True,**_public_value(result)})
   if len(z)>=4 and z[:2]==['api','events']:
    actor=request_actor(b)
    ctx=self._auth_ctx();
    if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
    rid=z[2];e=STORE.get(rid,ctx['household_id'] if ctx else None)
    if not e:raise NotFound('event_not_found')
    if z[3]=='organize':
     if ctx: STORE.authorize(self.headers.get('X-Auth-Token'),'organize',ctx['household_id'])
     expected=expected_version(b.get('expected_version'))
     if e['version']!=expected:raise Conflict('stale_version')
     related=[STORE.get(x) for x in e.get('related_record_ids',[])]; payload={**e,'history':related}
     safety=e['local_safety']
     try:
      r=organize_event(payload)
     except Exception as ex:
      # Do not expose provider bodies/credentials or misclassify storage/version
      # failures: only the provider+validation call is caught here.
      cause=ex.__cause__ or ex
      reason=('模型超时' if isinstance(cause,TimeoutError) else '模型返回非法 JSON' if isinstance(cause,json.JSONDecodeError) else '网络连接失败' if isinstance(cause,URLError) else '模型调用失败或返回内容未通过校验')
      failure={'error':'ai_organize_failed','failure_type':type(ex).__name__,'failure_cause_type':type(cause).__name__,'failure_reason':reason,'trace_id':'tr_'+secrets.token_hex(16),'raw_text_sha256':hashlib.sha256(e['raw_text'].encode()).hexdigest(),'prompt_version':'prompt-v0.4','schema_version':'event-v0.3','raw_text_preserved':True,'local_safety':safety}
      STORE.fail(rid,expected,'organize_failed',actor,failure)
      return self.send_json(422,{'ok':False,'ai_failed':True,'record_id':rid,'event':STORE.get(rid),'local_safety':safety,**failure,**safety})
     out=STORE.organize(rid,expected,r,actor)
     return self.send_json(200,{'event':out,'raw_text_preserved':True,**r})
    if z[3]=='review':
     if ctx: STORE.authorize(self.headers.get('X-Auth-Token'),'review',ctx['household_id'])
     return self.send_json(200,{'ok':True,'event':STORE.review(rid,b.get('expected_version'),b.get('action'),actor,b.get('note'))})
    if z[3]=='revise':
     if ctx: STORE.authorize(self.headers.get('X-Auth-Token'),'revise',ctx['household_id'])
     return self.send_json(201,{'ok':True,'event':STORE.revise(rid,b.get('expected_version'),b,actor)})
  except StoreError as e:return self.send_json(e.status,{'ok':False,'error':str(e)})
  except Exception:return self.send_json(500,{'ok':False,'error':'internal_server_error'})
  return self.send_json(404,{'ok':False,'error':'not_found'})
 def _do_media_upload_POST(self,p):
  self.media_write_enabled()
  backend=self.media_backend();key=self.headers.get('Idempotency-Key')
  if not key:raise StoreError('idempotency_key_required')
  ctx=self._auth_ctx('create')
  if self.headers.get('X-Auth-Token') and ctx is None:return self.send_json(401,{'ok':False,'error':'invalid_session'})
  household_id=ctx['household_id'] if ctx else None
  parts=p.strip('/').split('/')
  if p=='/api/media/uploads':
   fields,files=self.media_body()
   if files:raise StoreError('invalid_multipart_payload')
   try:total_parts=int(fields.get('total_parts',''))
   except ValueError:raise StoreError('expected_parts_must_positive_integer') from None
   metadata={
   'kind':fields.get('kind'),'content_type':fields.get('content_type'),
    'total_parts':total_parts,'expected_parts':total_parts,
    'original_filename':fields.get('original_filename'),
    'actor_name':fields.get('actor_name','老人'),
    'occurred_time':fields.get('occurred_time'),
   }
   if fields.get('expected_size') not in (None,''):
    try:metadata['expected_size']=int(fields['expected_size'])
    except ValueError:raise StoreError('expected_size_must_positive_integer') from None
   if fields.get('expected_sha256') not in (None,''):metadata['expected_sha256']=fields['expected_sha256']
   upload,created=backend.create_upload(metadata,key,household_id)
   return self.send_json(201 if created else 200,{'ok':True,'created':created,'upload':_public_value(upload)})
  if len(parts)==6 and parts[:3]==['api','media','uploads'] and parts[4]=='parts':
   upload_id=parts[3]
   if not _safe_media_id(upload_id,'upload'):return self.send_json(404,{'ok':False,'error':'not_found'})
   try:index=int(parts[5])
   except ValueError:return self.send_json(404,{'ok':False,'error':'not_found'})
   fields,files=self.media_body()
   if fields or set(files)!={'file'}:raise StoreError('invalid_multipart_payload')
   part,created=backend.write_part(upload_id,index,files['file']['data'],key,household_id)
   return self.send_json(201 if created else 200,{'ok':True,'created':created,'part':_public_value(part)})
  if len(parts)==5 and parts[:3]==['api','media','uploads'] and parts[4]=='complete':
   upload_id=parts[3]
   if not _safe_media_id(upload_id,'upload'):return self.send_json(404,{'ok':False,'error':'not_found'})
   body=self.body()
   if body:raise StoreError('complete_body_must_be_empty_object')
   media,created=backend.complete_upload(upload_id,key,household_id)
   return self.send_json(201 if created else 200,{'ok':True,'created':created,'media':_public_value(media)})
  return self.send_json(404,{'ok':False,'error':'not_found'})
def serve(host='127.0.0.1',port=None): ThreadingHTTPServer((host,int(os.getenv('API_PORT',port or 18768))),Handler).serve_forever()
if __name__=='__main__':serve()
