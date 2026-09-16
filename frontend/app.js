const API = globalThis.BingliConfig?.apiBaseUrl || '';
let token = localStorage.getItem('session_token') || '', modelProvider = '', saveBusy = false;
const PENDING_SAVE_KEY = 'elder_pending_save_v1';
let events = [], current = null, mediaRecorder = null, chunks = [], timerId = null, startedAt = 0, elapsedMs = 0, silenceTimer = null, demoMode = false, localMode = Boolean(globalThis.HealthLocal), voicePermissionPending = false, voiceUploadPending = false;
const handoffSelection=new Set(),knownHandoffEvents=new Set();
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
  views.forEach(v=>v.classList.toggle('active',v.id===id));document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===id));window.scrollTo({top:0,behavior:'smooth'});if(id==='recordsView')loadEvents();if(id==='homeView')renderHome();if(id==='settingsView')refreshStorageStatus()
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
  if(localMode){
    await globalThis.HealthLocal.initialise();
    try{const r=await fetch(API+'/health',{credentials:'include'});const j=await r.json();modelProvider=r.ok?j.provider:'';}catch{modelProvider='';}
    demoMode=false;setModeLabel();return true;
  }
  try {
    const r=await fetch(API+'/health',{credentials:'include'}); const j=await r.json();
    if(!r.ok || !j.ok || !j.session_token) throw new Error('backend unavailable');
    token=j.session_token; modelProvider=j.provider; demoMode=false; setModeLabel(); return true;
  } catch { demoMode=true; setModeLabel(); return false; }
}
function setModeLabel(){
  const p=$('modePill'); if(p)p.textContent=localMode?'本机加密保存':demoMode?'服务未连接 · 请重试':modelProvider==='mock'?'离线 Mock 演示模式':'本机记录中';
}
async function api(path,opt={},retried=false){
  if(localMode)return globalThis.HealthLocal.request(path,opt);
  const h={...(opt.body instanceof FormData ? {} : {'Content-Type':'application/json'}),...(opt.headers||{})};
  if(token)h['X-Session-Token']=token;
  try {
    const r=await fetch(API+path,{...opt,credentials:'include',headers:h}); let j={}; try{j=await r.json()}catch{}
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
function filteredEvents(){const keyword=$('filterKeyword')?.value.trim().toLowerCase()||'',kind=$('filterKind')?.value||'',state=$('filterState')?.value||'',start=$('filterStart')?.value?Date.parse($('filterStart').value+'T00:00:00'):null,end=$('filterEnd')?.value?Date.parse($('filterEnd').value+'T23:59:59.999'):null;return latestFirst(events.filter(e=>e.state!=='superseded')).filter(e=>{const at=Date.parse(e.recorded_at),haystack=`${e.raw_text||''} ${e.draft?.summary||''}`.toLowerCase();return (!keyword||haystack.includes(keyword))&&(!kind||e.draft?.event_kind===kind)&&(!state||e.state===state)&&(!start||at>=start)&&(!end||at<=end)})}
function renderList(){const box=$('eventsList');if(!box)return;const visible=filteredEvents();if(!visible.length){box.innerHTML=`<p class="muted">${events.some(e=>e.state!=='superseded')?'没有符合当前筛选的记录。':'还没有记录，先写下第一次情况吧。'}</p>`;return}box.innerHTML='';visible.forEach(e=>{if(!knownHandoffEvents.has(e.record_id)){knownHandoffEvents.add(e.record_id);handoffSelection.add(e.record_id)}const n=document.importNode($('eventTpl').content,true);n.querySelector('.event-date').textContent=`${dateText(e.recorded_at)} · ${stateLabel(e.state)}`;n.querySelector('.event-raw').textContent=e.raw_text;n.querySelector('.badges').innerHTML=(e.local_safety?.danger_detected?'<span class="badge warn">需要关注</span>':'')+(e.local_safety?.clinical_review_required?'<span class="badge warn">待专业复核</span>':'');const checkbox=n.querySelector('.handoff-select');checkbox.checked=handoffSelection.has(e.record_id);checkbox.onchange=()=>checkbox.checked?handoffSelection.add(e.record_id):handoffSelection.delete(e.record_id);n.querySelector('.view-btn').onclick=()=>showDetail(e.record_id);box.appendChild(n)})}
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
  let pending; if(!localMode)try{pending=JSON.parse(localStorage.getItem(PENDING_SAVE_KEY)||'null')}catch{}
  if(!pending || pending.body!==body)pending={key:crypto.randomUUID(),body};
  if(!localMode)localStorage.setItem(PENDING_SAVE_KEY,JSON.stringify(pending));
  const btn=$('saveBtn'); saveBusy=true;btn.disabled=true;btn.textContent='保存中…';
  if(demoMode)await health();
  const x=await api('/api/events',{method:'POST',headers:{'Idempotency-Key':pending.key},body});
  saveBusy=false;btn.disabled=false;btn.textContent='保存这条记录';
  if(x.r.ok){
    current=x.j.event;if(!localMode)localStorage.removeItem(PENDING_SAVE_KEY);
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
function detailHtml(e,{organizeFailed=false,relatedRecords=null}={}){const draft=draftHtml(e,{organizeFailed});return `<div class="section-head"><h2>记录详情</h2><button class="view-btn" onclick="closeDetail()">关闭</button></div><div class="event-date">${dateText(e.recorded_at)} · ${stateLabel(e.state)}</div><h3>原话</h3><div class="raw-box">${escapeHtml(e.raw_text)}</div>${safetyHtml(e.local_safety)}${draft}${relatedHistoryHtml(e,relatedRecords)}<div class="actions">${['inbox','needs_review'].includes(e.state)||(organizeFailed&&e.state==='draft')?'<button class="primary" id="organizeBtn">使用 AI 整理</button>':''}${e.state==='draft'&&!organizeFailed?'<button class="primary" id="reviewBtn">确认记录准确（非医学确认）</button><button class="outline" id="rejectBtn">退回重新整理</button>':''}<button class="outline" id="reviseBtn">保留历史并修订</button><button class="outline" id="historyBtn">查看历史</button>${localMode?'<button class="danger-button" id="deleteBtn">删除这条本机记录</button>':''}</div><div id="organizeStatus" role="status"></div>${e.supersedes_id?`<button class="outline" onclick="showDetail('${e.supersedes_id}')">查看修订前原文</button>`:''}<div id="subview"></div>`}
function renderDetail(e,options={}){
  current=e;safetyBanner(e.local_safety);
  const d=$('detail');d.classList.remove('hidden');d.innerHTML=detailHtml(e,options);d.scrollIntoView({behavior:'smooth'});
  if($('organizeBtn'))$('organizeBtn').onclick=()=>organize(e);
  if($('reviewBtn'))$('reviewBtn').onclick=()=>review(e,'confirm');
  if($('rejectBtn'))$('rejectBtn').onclick=()=>review(e,'reject');
  if($('deleteBtn'))$('deleteBtn').onclick=()=>deleteRecord(e);
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
  if(x.r.status===412){$('organizeStatus').textContent='已取消发送，本机原话仍安全保存。';toast('未发送给 AI');}
  else if(x.r.status===422){$('organizeStatus').textContent='原话已保存，AI 整理失败：'+(x.j.failure_reason||'请稍后重试');toast('原话已保存，整理暂时失败');}
  else if(x.r.ok&&x.j.event)toast('整理完成，请核对');
  else {toast(x.r.status===409?'记录已有新版本，请刷新后重试':'整理失败，原话仍在');b.disabled=false;b.textContent='整理记录';}
  await loadEvents();
}
async function review(e,action='confirm'){
  const b=$(action==='reject'?'rejectBtn':'reviewBtn');b.disabled=true;
  const x=await api('/api/events/'+e.record_id+'/review',{method:'POST',body:JSON.stringify({expected_version:e.version,action,note:action==='confirm'?'仅确认记录准确，不代表医生确认或风险消失':'退回重新整理'})});
  if(x.r.ok){toast(action==='confirm'?'已记录“记录准确”':'已退回重新整理');await loadEvents();await showDetail(e.record_id);}
  else {b.disabled=false;toast('核对未确认，请刷新后重试');}
}
async function deleteRecord(e){
  if(!confirm('删除会移除这条记录、它的本机修订历史和已关联原件。已下载或已上传的旧密文备份不会自动改变。继续吗？'))return;
  if(!confirm('请再确认一次：只删除选中的本机记录，不删除恢复口令、API 密钥或其他记录。'))return;
  const x=await api('/api/events/'+e.record_id,{method:'DELETE',body:JSON.stringify({delete_scope_confirmed:true})});
  if(x.r.ok){closeDetail();await loadEvents();toast(`已删除本机记录${x.j.deleted.local_media_count?`和 ${x.j.deleted.local_media_count} 份关联原件`:''}；旧备份未改变`)}else toast('删除未完成，数据仍保留');
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
  const handoffBody=localMode?JSON.stringify({start_date:$('handoffStart')?.value||null,end_date:$('handoffEnd')?.value||null,record_ids:[...handoffSelection]}):'{}';
  const x=await api('/api/handoffs',{method:'POST',body:handoffBody});b.disabled=false;b.textContent='生成就诊交接材料';
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
for(const id of ['filterKeyword','filterKind','filterState','filterStart','filterEnd'])$(id)?.addEventListener(id==='filterKeyword'?'input':'change',renderList);
if($('clearFilters'))$('clearFilters').onclick=()=>{for(const id of ['filterKeyword','filterKind','filterState','filterStart','filterEnd'])$(id).value='';renderList()};
async function refreshStorageStatus(){if(!localMode||!$('storageStatus'))return;try{const s=await HealthLocal.storageStatus(),used=(s.usage/1024/1024).toFixed(1),quota=s.quota?`${(s.quota/1024/1024).toFixed(0)} MB`:'未知';$('storageStatus').textContent=`已使用约 ${used} MB / 可用额度 ${quota}。${s.persisted?'浏览器已批准持久存储。':'浏览器尚未批准持久存储，请定期下载备份。'}`}catch{$('storageStatus').textContent='无法读取本机存储额度，请定期下载加密备份。'}}
async function restoreEncryptedBackup(file,status){const passphrase=prompt('输入这份备份的恢复口令。口令只在当前设备验证，不会上传。');if(!passphrase){status.textContent='已取消恢复，当前数据未改变。';return false}try{const preview=await HealthLocal.previewBackup(file,passphrase);if(!confirm(`备份中有 ${preview.eventCount} 条记录、${preview.mediaCount} 份原件，导出时间 ${preview.exportedAt||'未知'}。恢复将替换当前设备的数据，是否继续？`)){status.textContent='已取消，当前数据未改变。';return false}await HealthLocal.restoreBackup(preview,passphrase);status.textContent='恢复完成，正在重新读取记录。';await loadEvents();return true}catch{status.textContent='备份无法验证或已损坏，当前数据未被覆盖。';return false}}
function renderCloudBackups(backups){const box=$('cloudBackups');if(!box)return;box.replaceChildren();if(!backups.length){const empty=document.createElement('p');empty.className='muted';empty.textContent='私有云里还没有加密备份。';box.append(empty);return}for(const item of backups){const row=document.createElement('div');row.className='cloud-backup-row';const copy=document.createElement('div'),title=document.createElement('b'),meta=document.createElement('span'),button=document.createElement('button');title.textContent='加密备份';const when=item.last_modified?new Date(item.last_modified).toLocaleString():'时间未知',size=Number.isFinite(item.size)?`${(item.size/1024/1024).toFixed(2)} MB`:'大小未知';meta.textContent=`${when} · ${size}`;copy.append(title,meta);button.className='outline';button.textContent='验证并恢复';button.onclick=async()=>{const status=$('cloudBackupStatus');button.disabled=true;status.textContent='正在取得这份密文备份…';try{const file=await HealthLocal.downloadCloudBackup(item.object_key);await restoreEncryptedBackup(file,status)}catch{status.textContent='云备份下载失败，当前数据未改变。'}finally{button.disabled=false}};row.append(copy,button);box.append(row)}}
async function refreshCloudBackups(){const status=$('cloudBackupStatus');if(!status)return;status.textContent='正在读取私有云中的密文备份…';try{const backups=await HealthLocal.listCloudBackups();renderCloudBackups(backups);status.textContent=`找到 ${backups.length} 份密文备份。恢复前仍会验证恢复口令。`}catch{status.textContent='暂时无法读取云备份；本机资料不受影响。'}}
async function refreshCloudBackupConfig(){if(!localMode||!$('uploadCloudBackupBtn'))return;try{const response=await fetch(globalThis.BingliConfig.apiUrl('/api/app/config'),{credentials:'include'}),config=await response.json(),enabled=response.ok&&config.cloud_backup_configured===true;$('uploadCloudBackupBtn').disabled=!enabled;$('refreshCloudBackupsBtn').disabled=!enabled;$('cloudBackupStatus').textContent=enabled?'私有云备份已开通；只会上传当前设备生成的加密包。':'私有云备份尚未开通，仍可下载加密备份文件。'}catch{$('cloudBackupStatus').textContent='无法检查云备份配置，仍可下载加密备份文件。'}}
if($('downloadBackupBtn'))$('downloadBackupBtn').onclick=async()=>{const s=$('backupStatus');try{await HealthLocal.downloadBackup();s.textContent='加密备份已生成，请确认浏览器的下载位置。'}catch{s.textContent='备份生成失败，本机数据未改变。'}};
if($('restoreBackupInput'))$('restoreBackupInput').onchange=async e=>{const file=e.target.files?.[0],s=$('backupStatus');e.target.value='';if(file)await restoreEncryptedBackup(file,s)};
if($('uploadCloudBackupBtn'))$('uploadCloudBackupBtn').onclick=async()=>{const button=$('uploadCloudBackupBtn'),status=$('cloudBackupStatus');if(!confirm('将把当前设备生成的加密备份包上传到你的私有 TOS。云端只能看到密文、大小和备份时间，恢复口令不会上传。是否继续？'))return;button.disabled=true;status.textContent='正在生成并上传密文备份，请不要关闭页面…';try{const saved=await HealthLocal.uploadCloudBackup();status.textContent=`云备份完成，共 ${(saved.size/1024/1024).toFixed(2)} MB。`;await refreshCloudBackups()}catch{status.textContent='云备份失败，本机资料和已有备份未改变。'}finally{button.disabled=false}};
if($('refreshCloudBackupsBtn'))$('refreshCloudBackupsBtn').onclick=refreshCloudBackups;
if($('lockVaultBtn'))$('lockVaultBtn').onclick=()=>{HealthLocal.lock();location.reload()};
if($('saveFeedbackBtn'))$('saveFeedbackBtn').onclick=async()=>{const text=$('feedbackText').value,s=$('feedbackStatus');try{await HealthLocal.saveFeedback(text,document.querySelector('.view.active')?.id);$('feedbackText').value='';s.textContent='内测问题已加密保存在本机，未附带健康原文。'}catch{s.textContent='请先写下问题描述（不要粘贴密钥）。'}};
if(!localMode)try {const pending=JSON.parse(localStorage.getItem(PENDING_SAVE_KEY)||'null');if(pending)$('rawText').value=JSON.parse(pending.body).raw_text;}catch{}
health().then(loadEvents);refreshCloudBackupConfig();
if(typeof navigator!=='undefined'&&'serviceWorker'in navigator&&location.protocol==='https:')navigator.serviceWorker.register('/service-worker.js').catch(()=>{});
