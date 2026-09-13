const API = ['localhost','127.0.0.1'].includes(location.hostname) && location.port === '5173' ? `http://${location.hostname}:18768` : '';
let token = localStorage.getItem('session_token') || '', modelProvider = '', saveBusy = false;
const PENDING_SAVE_KEY = 'elder_pending_save_v1';
let events = [], current = null, mediaRecorder = null, chunks = [], timerId = null, startedAt = 0, elapsedMs = 0, silenceTimer = null, demoMode = false, voicePermissionPending = false, voiceUploadPending = false;
const DEMO_KEY = 'elder_demo_events_v1';
const PHOTO_KEY = 'elder_demo_photos_v1';
const $ = id => document.getElementById(id);
const views = [...document.querySelectorAll('.view')];
function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2600)}
function clearRecordPanels(){
  const detail=$('detail');if(detail){detail.classList.add('hidden');detail.innerHTML=''}
  const handoff=$('handoff');if(handoff){handoff.classList.add('hidden');handoff.innerHTML=''}
  const banner=$('dangerBanner');if(banner){banner.classList.add('hidden');banner.innerHTML=''}
  current=null;
}
function showView(id){
  // Detail, handoff and the fixed safety banner belong to the records view.
  // Clear them whenever navigation starts so an older event cannot leak into
  // a different screen or appear as if it were the newly selected record.
  clearRecordPanels();
  views.forEach(v=>v.classList.toggle('active',v.id===id));document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===id));window.scrollTo({top:0,behavior:'smooth'});if(id==='recordsView')loadEvents();if(id==='homeView')renderHome()
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{
  // Media entry buttons are disabled after capability discovery when the
  // running instance cannot safely accept uploads.  Keep the guard here as
  // well as the DOM disabled state because some touch/browser shims still
  // dispatch a click for a disabled button.
  if(b.disabled)return;
  showView(b.dataset.view)
}));
async function health(){
  try {
    const r=await fetch(API+'/health'); const j=await r.json();
    if(!r.ok || !j.ok || !j.session_token) throw new Error('backend unavailable');
    token=j.session_token; modelProvider=j.provider; demoMode=false; setModeLabel(); return true;
  } catch { demoMode=true; setModeLabel(); return false; }
}
function setModeLabel(){
  const p=$('modePill'); if(p)p.textContent=demoMode?'服务未连接 · 请重试':modelProvider==='mock'?'离线 Mock 演示模式':'本机记录中';
}
async function api(path,opt={},retried=false){
  const h={...(opt.body instanceof FormData ? {} : {'Content-Type':'application/json'}),...(opt.headers||{})};
  if(token)h['X-Session-Token']=token;
  try {
    const r=await fetch(API+path,{...opt,headers:h}); let j={}; try{j=await r.json()}catch{}
    // Restart rotates the local session token. A rejected request has no side effect.
    if(r.status===403 && j.error==='csrf_or_origin_rejected' && !retried && await health())return api(path,opt,true);
    return {r,j};
  } catch { demoMode=true; setModeLabel(); return {r:{ok:false,status:0},j:{}}; }
}
function safetyHtml(s){
  let html='';
  if(s?.danger_detected)html+=`<p class="status error">${s.historical_notice_preserved?'历史记录曾触发提醒：':''}${escapeHtml(s.danger_reminder||'请联系当地急救服务或专业人员，不要自行改药。')}</p>`;
  if(s?.clinical_review_required)html+=`<p class="status error">${escapeHtml(s.clinical_review_notice||'这条记录需要专业人员复核，记录核对不能消除待办。')}</p>`;
  return html;
}
function safetyBanner(s){const b=$('dangerBanner');if(!b)return;if(s?.danger_detected){b.innerHTML=`<b>需要及时关注</b><br>${escapeHtml(s.danger_reminder||'记录中出现需要尽快请专业人员判断的描述，请联系当地急救服务或专业人员。')}`;b.classList.remove('hidden')}else b.classList.add('hidden')}
function stateLabel(s){return ({inbox:'已保存，待整理',draft:'整理草稿，待核对',needs_review:'退回待整理',recorded:'已核对记录准确',superseded:'旧版本'})[s]||s}
const EVENT_KIND_LABELS={symptom:'症状记录',measurement:'指标记录',medication:'用药记录',instruction:'医嘱或建议',document:'资料记录',question:'待核对问题',handoff:'交接记录',other:'其他记录'};
const REVIEW_ROLE_LABELS={none:'暂未指定',family:'家属或照护者',clinician_or_pharmacist:'医生、护士或药师',emergency_services:'急救服务或专业人员'};
const ESCALATION_LABELS={none:'常规核对',urgent:'尽快核对',emergency:'需要及时关注'};
const CERTAINTY_LABELS={exact:'具体时间',range:'时间范围',daypart:'时段',relative:'原话中的相对时间',unknown:'时间未说明'};
const SOURCE_KIND_LABELS={elder:'老人自述',family_observation:'家属观察',family_report:'家属转述',caregiver:'照护员记录',clinician_evidence:'医生或药师资料',document:'资料摘要',audio_transcript:'录音转写',system:'系统记录',unknown:'来源未标明'};
function dateText(v){return v?new Date(v).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):''}
function renderArchive(){
  const ebox=$('archiveEvents'); if(!ebox)return;
  const active=latestFirst(events.filter(e=>e.state!=='superseded')); $('archiveEventCount').textContent=active.length;
  ebox.innerHTML=active.length?active.slice(0,3).map(e=>`<button class="recent-item" data-id="${e.record_id}"><span class="date">${dateText(e.recorded_at)} · ${stateLabel(e.state)}</span><p>${escapeHtml(e.raw_text)}</p></button>`).join(''):'<p class="muted">还没有症状记录</p>';
  ebox.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>{showView('recordsView');showDetail(b.dataset.id)});
}
function latestFirst(items){return items.slice().sort((a,b)=>{const at=Date.parse(a.recorded_at||a.created_at||a.updated_at||'')||0;const bt=Date.parse(b.recorded_at||b.created_at||b.updated_at||'')||0;return bt-at||String(b.record_id||b.media_id||'').localeCompare(String(a.record_id||a.media_id||''))})}
function renderHome(){const box=$('homeRecent');if(!box)return;if(!events.length){box.innerHTML='<p class="muted">还没有记录，先说下今天的情况吧。</p>';return}box.innerHTML=latestFirst(events.filter(e=>e.state!=='superseded')).slice(0,3).map(e=>`<button class="recent-item" data-id="${e.record_id}"><span class="date">${dateText(e.recorded_at)} · ${stateLabel(e.state)}</span><p>${escapeHtml(e.raw_text)}</p></button>`).join('');box.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>{showView('recordsView');setTimeout(()=>showDetail(b.dataset.id),80)})}
function renderList(){const box=$('eventsList');if(!box)return;if(!events.length){box.innerHTML='<p class="muted">还没有记录，先写下第一次情况吧。</p>';return}box.innerHTML='';latestFirst(events.filter(e=>e.state!=='superseded')).forEach(e=>{const n=document.importNode($('eventTpl').content,true);n.querySelector('.event-date').textContent=`${dateText(e.recorded_at)} · ${stateLabel(e.state)}`;n.querySelector('.event-raw').textContent=e.raw_text;n.querySelector('.badges').innerHTML=e.local_safety?.danger_detected?'<span class="badge warn">需要关注</span>':'';n.querySelector('.view-btn').onclick=()=>showDetail(e.record_id);box.appendChild(n)})}
async function loadEvents(){
  const {r,j}=await api('/api/events');
  if(r.ok){demoMode=false;events=j.events||[];setModeLabel();renderList();renderHome();renderArchive();}
  else {demoMode=true;setModeLabel();toast('记录暂时无法读取，请恢复连接后刷新；已保存内容不会删除');}
}
async function save(){
  if(saveBusy)return;
  const text=$('rawText').value;
  if(!text.trim()){$('saveStatus').textContent='请先写下发生的情况';return;}
  const body=JSON.stringify({raw_text:text,source_kind:'elder',actor_name:'老人'});
  let pending; try{pending=JSON.parse(localStorage.getItem(PENDING_SAVE_KEY)||'null')}catch{}
  if(!pending || pending.body!==body)pending={key:crypto.randomUUID(),body};
  localStorage.setItem(PENDING_SAVE_KEY,JSON.stringify(pending));
  const btn=$('saveBtn'); saveBusy=true;btn.disabled=true;btn.textContent='保存中…';
  if(demoMode)await health();
  const x=await api('/api/events',{method:'POST',headers:{'Idempotency-Key':pending.key},body});
  saveBusy=false;btn.disabled=false;btn.textContent='保存这条记录';
  if(x.r.ok){
    current=x.j.event;localStorage.removeItem(PENDING_SAVE_KEY);
    $('saveStatus').textContent='✓ 原话已保存';$('saveStatus').className='status ok';$('rawText').value='';
    await loadEvents();showView('recordsView');await showDetail(x.j.event.record_id);
  } else {$('saveStatus').textContent='保存未确认，请重试。原输入保留，重试不会重复建记录。';$('saveStatus').className='status error';}
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function listHtml(items,empty='暂无'){const values=Array.isArray(items)?items.filter(v=>typeof v==='string'&&v.trim()):[];return values.length?`<ul class="plain-list">${values.map(v=>`<li>${escapeHtml(v)}</li>`).join('')}</ul>`:`<p class="muted">${empty}</p>`}
function draftHtml(e,{organizeFailed=false}={}){
  const d=e.draft;if(!d||typeof d!=='object')return '';
  const time=d.time&&typeof d.time==='object'?d.time:{};
  const occurred=time.occurred?escapeHtml(dateText(time.occurred)||String(time.occurred)):'未提供具体日期';
  const certainty=CERTAINTY_LABELS[time.certainty]||'时间未说明';
  const role=REVIEW_ROLE_LABELS[d.review_role]||'需要人工核对';
  const level=ESCALATION_LABELS[d.escalation_level]||'需要人工核对';
  const extra=Object.entries(d).filter(([key,value])=>!['schema_version','event_kind','summary','time','claims','review_required','review_role','escalation_level','conflict','provenance_preserved','plan_change_allowed','follow_up_questions','forbidden_actions'].includes(key)&&typeof value==='string'&&value.trim()).map(([,value])=>value);
  return `<section class="draft-card"><h3>${organizeFailed?'上次整理草稿（本次整理失败，未更新）':'整理结果（请核对）'}</h3><p class="draft-note">这是结构化草稿，不是诊断，也不会自动改变用药方案。</p><div class="fact-grid"><div><span>记录类型</span><b>${escapeHtml(EVENT_KIND_LABELS[d.event_kind]||'待人工判断')}</b></div><div><span>发生时间</span><b>${occurred}<small>${escapeHtml(certainty)}</small></b></div><div><span>需要谁核对</span><b>${escapeHtml(role)}</b></div><div><span>关注级别</span><b>${escapeHtml(level)}</b></div></div><div class="draft-source"><b>原话已完整保留</b><span>AI 只做分类和归档，没有改写原文。</span></div>${d.follow_up_questions?.length?`<h4>待核对问题</h4>${listHtml(d.follow_up_questions)}`:''}${d.conflict?.present?`<p class="status error">发现不同记录，需要把双方原话一起交给人工核对。</p>`:''}${extra.length?`<h4>补充说明</h4>${listHtml(extra)}`:''}</section>`;
}
function relatedHistoryHtml(e,records){
  const ids=Array.isArray(e.related_record_ids)?e.related_record_ids:[];
  if(!ids.length)return '';
  if(!records)return '<section class="related-history"><h3>相关历史线索</h3><p class="muted">正在读取已关联的历史原话…</p></section>';
  const rows=records.length?records.map(item=>`<article class="history-source"><b>${escapeHtml(SOURCE_KIND_LABELS[item.source_kind]||'历史记录')} · ${dateText(item.recorded_at)}</b><p>${escapeHtml(item.raw_text)}</p></article>`).join(''):'<p class="muted">未能读取关联历史原话；不会用摘要替代原文。</p>';
  return `<section class="related-history"><h3>相关历史线索（需要核对）</h3><p class="draft-note">以下内容来自已关联的原始记录，只用于提出核对问题，不代表当前症状已经找到病因。</p>${rows}<p class="related-question">请由老人、家属或医生核对：这次记录是否与以上历史有关？如不确定，以医生判断为准。</p></section>`;
}
function detailHtml(e,{organizeFailed=false,relatedRecords=null}={}){const draft=draftHtml(e,{organizeFailed});return `<div class="section-head"><h2>记录详情</h2><button class="view-btn" onclick="closeDetail()">关闭</button></div><div class="event-date">${dateText(e.recorded_at)} · ${stateLabel(e.state)}</div><h3>原话</h3><div class="raw-box">${escapeHtml(e.raw_text)}</div>${safetyHtml(e.local_safety)}${draft}${relatedHistoryHtml(e,relatedRecords)}<div class="actions">${['inbox','needs_review'].includes(e.state)||(organizeFailed&&e.state==='draft')?'<button class="primary" id="organizeBtn">整理记录</button>':''}${e.state==='draft'&&!organizeFailed?'<button class="primary" id="reviewBtn">我核对过了</button>':''}<button class="outline" id="reviseBtn">修订记录</button><button class="outline" id="historyBtn">查看历史</button></div><div id="organizeStatus" role="status"></div>${e.supersedes_id?`<button class="outline" onclick="showDetail('${e.supersedes_id}')">查看修订前原文</button>`:''}<div id="subview"></div>`}
function renderDetail(e,options={}){
  current=e;safetyBanner(e.local_safety);
  const d=$('detail');d.classList.remove('hidden');d.innerHTML=detailHtml(e,options);d.scrollIntoView({behavior:'smooth'});
  if($('organizeBtn'))$('organizeBtn').onclick=()=>organize(e);
  if($('reviewBtn'))$('reviewBtn').onclick=()=>review(e);
  $('reviseBtn').onclick=()=>revise(e);$('historyBtn').onclick=()=>historyView(e);
}
async function loadRelatedHistory(e){const ids=Array.isArray(e.related_record_ids)?e.related_record_ids.slice(0,10):[];if(!ids.length)return;const records=[];for(const id of ids){const x=await api('/api/events/'+encodeURIComponent(id));if(x.r.ok&&x.j.event)records.push(x.j.event)}if(current?.record_id===e.record_id)renderDetail(e,{relatedRecords:records})}
async function showDetail(id){const {r,j}=await api('/api/events/'+id);if(!r.ok){toast('详情读取失败，请重试');return;}renderDetail(j.event);loadRelatedHistory(j.event)}
function closeDetail(){clearRecordPanels()}
async function organize(e){
  const b=$('organizeBtn');if(!b||b.disabled)return;b.disabled=true;b.textContent='整理中…';
  const x=await api('/api/events/'+e.record_id+'/organize',{method:'POST',body:JSON.stringify({expected_version:e.version})});
  // A successful POST or 422 already carries the saved evidence. Render it
  // without a second GET, so losing the connection cannot hide the original.
  if(x.j.event||x.r.status===422){
    const saved=x.j.event||e;
    renderDetail({...saved,local_safety:{...saved.local_safety,...x.j.local_safety}},{organizeFailed:x.r.status===422});
    loadRelatedHistory(saved);
  }
  if(x.r.status===422){$('organizeStatus').textContent='原话已保存，AI 整理失败：'+(x.j.failure_reason||'请稍后重试');toast('原话已保存，整理暂时失败');}
  else if(x.r.ok&&x.j.event)toast('整理完成，请核对');
  else {toast(x.r.status===409?'记录已有新版本，请刷新后重试':'整理失败，原话仍在');b.disabled=false;b.textContent='整理记录';}
  await loadEvents();
}
async function review(e){
  const b=$('reviewBtn');b.disabled=true;
  const x=await api('/api/events/'+e.record_id+'/review',{method:'POST',body:JSON.stringify({expected_version:e.version,action:'confirm',note:'仅确认记录准确'})});
  if(x.r.ok){toast('已记录“核对准确”');await loadEvents();await showDetail(e.record_id);}
  else {b.disabled=false;toast('核对未确认，请刷新后重试');}
}
function revise(e){
  $('subview').innerHTML=`<h3>修订记录</h3><textarea id="revText" rows="4">${escapeHtml(e.raw_text)}</textarea><input id="revReason" placeholder="修订原因（必填）" class="time-label"><button class="primary" id="submitRev">保存修订</button><div id="reviseStatus" role="status"></div>`;
  const button=$('submitRev'),status=$('reviseStatus');let busy=false;
  button.onclick=async()=>{
    if(busy)return;
    const raw=$('revText').value.trim(),reason=$('revReason').value.trim();
    if(!raw||!reason){toast('请填写内容和修订原因');return}
    busy=true;button.disabled=true;button.textContent='保存中…';status.textContent='正在保存修订…';
    try{
      const x=await api('/api/events/'+e.record_id+'/revise',{method:'POST',body:JSON.stringify({raw_text:raw,source_kind:'elder',actor_name:'老人',expected_version:e.version,reason})});
      if(x.r.ok&&x.j.event){renderDetail(x.j.event);toast('修订已保存');await loadEvents()}
      else {status.textContent=x.r.status===409?'记录已有新版本，输入已保留，请核对最新记录后再修订。':'修订保存未确认，输入已保留，请恢复连接后重试。';toast(status.textContent)}
    }finally{busy=false;button.disabled=false;button.textContent='保存修订'}
  };
}
async function historyView(e){const x=await api('/api/events/'+e.record_id+'/history');if(!x.r.ok)return;$('subview').innerHTML='<h3>历史记录</h3><div class="history">'+(x.j.history||[]).map(h=>`<div class="history-item"><b>${h.action}</b> · v${h.version}<br><span class="muted">${new Date(h.at).toLocaleString('zh-CN')}</span><p>${escapeHtml(h.snapshot?.raw_text||'')}</p>${safetyHtml(h.snapshot?.local_safety)}</div>`).join('')+'</div>'}
async function handoff(){
  const b=$('handoffBtn');b.disabled=true;b.textContent='生成中…';
  const x=await api('/api/handoffs',{method:'POST',body:'{}'});b.disabled=false;b.textContent='生成就诊交接材料';
  if(!x.r.ok){toast('生成失败，请重试');return;}
  const h=x.j.handoff,box=$('handoff');box.classList.remove('hidden');
  box.innerHTML=`<div class="section-head"><h2>就诊交接材料</h2><button class="view-btn" onclick="window.print()">打印</button></div><p class="muted">生成于 ${dateText(h.created_at)} · ${h.unresolved_count||0} 项待处理。核对只确认记录准确，不代表医学风险已消除。</p>`+
    (h.items||[]).map(i=>`<div class="handoff-item"><b>${dateText(i.recorded_at)} · ${escapeHtml(i.source_kind)} · ${stateLabel(i.state)}</b><p>${escapeHtml(i.raw_text)}</p>${safetyHtml(i.local_safety)}${i.unresolved?'<span class="badge warn">仍有待处理事项</span>':''}</div>`).join('')+
    '<h3>媒体原件与待处理状态</h3>'+(h.media_attachments||[]).map(m=>`<div class="handoff-item">${escapeHtml(m.kind)} · ${escapeHtml(m.recognition_status)} · ${escapeHtml(m.link_status)}${m.is_mock?' · 离线 Mock 演示模式':''}${m.unresolved?'<p>原件已保留，仍待识别或核对</p>':''}${safetyHtml(m.local_safety)}</div>`).join('');
  box.scrollIntoView({behavior:'smooth'});
}
function updateTimer(){const active=mediaRecorder?.state==='recording'?Date.now()-startedAt:0;const sec=Math.floor((elapsedMs+active)/1000);$('voiceTimer').textContent=`${String(Math.floor(sec/60)).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`}
function setRecording(on){$('recordBtn').classList.toggle('recording',on);$('recordBtn').disabled=voicePermissionPending||voiceUploadPending;$('recordBtn').querySelector('span').textContent=voicePermissionPending?'等待麦克风权限…':voiceUploadPending?'请先保存上一段录音':on?'正在说…':mediaRecorder?.state==='paused'?'继续说':'开始说';$('finishVoiceBtn').disabled=voicePermissionPending||voiceUploadPending||!(on||mediaRecorder?.state==='paused');$('wave').classList.toggle('active',on)}
function armSilenceTimer(){clearTimeout(silenceTimer);silenceTimer=setTimeout(()=>{if(mediaRecorder?.state==='recording'||$('recordBtn').classList.contains('recording')){pauseVoice('好像停了一会儿',true)}},12000)}
function pauseVoice(reason='已暂停，可以继续说',showNotice=false){
  if(mediaRecorder?.state==='recording'){elapsedMs+=Date.now()-startedAt;mediaRecorder.pause()}
  clearInterval(timerId);timerId=null;clearTimeout(silenceTimer);updateTimer();setRecording(false);
  $('voiceHint').textContent=reason;
  if(showNotice)$('silenceNotice').classList.remove('hidden');
}
function resumeVoice(){
  if(mediaRecorder?.state==='paused'){
    mediaRecorder.resume();startedAt=Date.now();timerId=setInterval(updateTimer,1000);updateTimer();setRecording(true);
    $('silenceNotice').classList.add('hidden');$('voiceHint').textContent='继续听，请慢慢说';armSilenceTimer();
  } else if(!mediaRecorder){
    startVoice();
  }
}
async function startVoice(){
  if(voicePermissionPending||voiceUploadPending)return;
  if(mediaRecorder?.state==='recording'||$('recordBtn').classList.contains('recording')){pauseVoice('手动暂停');return}
  if(mediaRecorder?.state==='paused'){resumeVoice();return}
  chunks=[];elapsedMs=0;clearInterval(timerId);timerId=null;updateTimer();voicePermissionPending=true;setRecording(false);$('voiceHint').textContent='请允许使用麦克风，授权后才开始录音';
  let stream;
  try{
    stream=await navigator.mediaDevices.getUserMedia({audio:true});
    mediaRecorder=new MediaRecorder(stream);
    const recordingChunks=chunks;
    mediaRecorder.ondataavailable=e=>{if(e.data.size)recordingChunks.push(e.data)};
    mediaRecorder.onstop=()=>stream.getTracks().forEach(t=>t.stop());
    mediaRecorder.start();startedAt=Date.now();timerId=setInterval(updateTimer,1000);$('voiceHint').textContent='正在听，请慢慢说';armSilenceTimer();
  }catch(e){
    stream?.getTracks().forEach(t=>t.stop());mediaRecorder=null;clearInterval(timerId);timerId=null;clearTimeout(silenceTimer);$('voiceHint').textContent='麦克风未能开启，请检查权限，或使用文字补充、上传已有录音';
  }finally{voicePermissionPending=false;setRecording(mediaRecorder?.state==='recording');updateTimer()}
}
function stopVoice(reason){
  if(mediaRecorder?.state==='recording')elapsedMs+=Date.now()-startedAt;
  clearInterval(timerId);timerId=null;clearTimeout(silenceTimer);
  if(mediaRecorder?.state==='recording'||mediaRecorder?.state==='paused')mediaRecorder.stop();
  mediaRecorder=null;updateTimer();setRecording(false);$('voiceHint').textContent=reason||'这一段已暂存';$('silenceNotice').classList.add('hidden')
}
$('recordBtn').onclick=startVoice;$('resumeBtn').onclick=resumeVoice;$('pauseBtn').onclick=()=>pauseVoice('已暂停，可以稍后继续说');$('saveBtn').onclick=save;$('refreshBtn').onclick=async()=>{await health();await loadEvents();toast('记录已刷新')};$('handoffBtn').onclick=handoff;
try {const pending=JSON.parse(localStorage.getItem(PENDING_SAVE_KEY)||'null');if(pending)$('rawText').value=JSON.parse(pending.body).raw_text;}catch{}
health().then(loadEvents);
