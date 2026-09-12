const API = ['localhost','127.0.0.1'].includes(location.hostname) && location.port === '5173' ? `http://${location.hostname}:18768` : '';
let token = localStorage.getItem('session_token') || '', modelProvider = '', saveBusy = false;
const PENDING_SAVE_KEY = 'elder_pending_save_v1';
let events = [], current = null, mediaRecorder = null, chunks = [], timerId = null, startedAt = 0, silenceTimer = null, demoMode = false;
const DEMO_KEY = 'elder_demo_events_v1';
const PHOTO_KEY = 'elder_demo_photos_v1';
const $ = id => document.getElementById(id);
const views = [...document.querySelectorAll('.view')];
function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2600)}
function showView(id){views.forEach(v=>v.classList.toggle('active',v.id===id));document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===id));window.scrollTo({top:0,behavior:'smooth'});if(id==='recordsView')loadEvents();if(id==='homeView')renderHome()}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.view)));
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
function dateText(v){return v?new Date(v).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):''}
function renderArchive(){
  const ebox=$('archiveEvents'); if(!ebox)return;
  const active=events.filter(e=>e.state!=='superseded'); $('archiveEventCount').textContent=active.length;
  ebox.innerHTML=active.length?active.slice(0,3).map(e=>`<button class="recent-item" data-id="${e.record_id}"><span class="date">${dateText(e.recorded_at)} · ${stateLabel(e.state)}</span><p>${escapeHtml(e.raw_text)}</p></button>`).join(''):'<p class="muted">还没有症状记录</p>';
  ebox.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>{showView('recordsView');showDetail(b.dataset.id)});
}
function renderHome(){const box=$('homeRecent');if(!box)return;if(!events.length){box.innerHTML='<p class="muted">还没有记录，先说下今天的情况吧。</p>';return}box.innerHTML=events.filter(e=>e.state!=='superseded').slice(0,3).map(e=>`<button class="recent-item" data-id="${e.record_id}"><span class="date">${dateText(e.recorded_at)} · ${stateLabel(e.state)}</span><p>${escapeHtml(e.raw_text)}</p></button>`).join('');box.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>{showView('recordsView');setTimeout(()=>showDetail(b.dataset.id),80)})}
function renderList(){const box=$('eventsList');if(!box)return;if(!events.length){box.innerHTML='<p class="muted">还没有记录，先写下第一次情况吧。</p>';return}box.innerHTML='';events.filter(e=>e.state!=='superseded').forEach(e=>{const n=document.importNode($('eventTpl').content,true);n.querySelector('.event-date').textContent=`${dateText(e.recorded_at)} · ${stateLabel(e.state)}`;n.querySelector('.event-raw').textContent=e.raw_text;n.querySelector('.badges').innerHTML=e.local_safety?.danger_detected?'<span class="badge warn">需要关注</span>':'';n.querySelector('.view-btn').onclick=()=>showDetail(e.record_id);box.appendChild(n)})}
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
function detailHtml(e){const draft=e.draft?`<h3>整理草稿（请核对）</h3><div class="raw-box">${escapeHtml(JSON.stringify(e.draft,null,2))}</div>`:'';return `<div class="section-head"><h2>记录详情</h2><button class="view-btn" onclick="closeDetail()">关闭</button></div><div class="event-date">${dateText(e.recorded_at)} · ${stateLabel(e.state)}</div><h3>原话</h3><div class="raw-box">${escapeHtml(e.raw_text)}</div>${safetyHtml(e.local_safety)}${draft}<div class="actions">${['inbox','needs_review'].includes(e.state)?'<button class="primary" id="organizeBtn">整理记录</button>':''}${e.state==='draft'?'<button class="primary" id="reviewBtn">我核对过了</button>':''}<button class="outline" id="reviseBtn">修订记录</button><button class="outline" id="historyBtn">查看历史</button></div><div id="organizeStatus" role="status"></div>${e.supersedes_id?`<button class="outline" onclick="showDetail('${e.supersedes_id}')">查看修订前原文</button>`:''}<div id="subview"></div>`}
async function showDetail(id){const {r,j}=await api('/api/events/'+id);if(!r.ok){toast('详情读取失败，请重试');return;}current=j.event;safetyBanner(current.local_safety);const d=$('detail');d.classList.remove('hidden');d.innerHTML=detailHtml(current);d.scrollIntoView({behavior:'smooth'});if($('organizeBtn'))$('organizeBtn').onclick=()=>organize(current);if($('reviewBtn'))$('reviewBtn').onclick=()=>review(current);$('reviseBtn').onclick=()=>revise(current);$('historyBtn').onclick=()=>historyView(current)}
function closeDetail(){$('detail').classList.add('hidden')}
async function organize(e){
  const b=$('organizeBtn');b.disabled=true;b.textContent='整理中…';
  const x=await api('/api/events/'+e.record_id+'/organize',{method:'POST',body:JSON.stringify({expected_version:e.version})});
  // Render the 422 saved event directly, even when the subsequent GET is offline.
  if(x.j.event){current=x.j.event;await showDetail(e.record_id);safetyBanner(x.j.local_safety||current.local_safety);}
  if(x.r.status===422){$('organizeStatus').textContent='原话已保存，AI 整理失败：'+(x.j.failure_reason||'请稍后重试');toast('原话已保存，整理暂时失败');}
  else if(x.r.ok)toast('整理完成，请核对');
  else {toast(x.r.status===409?'记录已有新版本，请刷新后重试':'整理失败，原话仍在');b.disabled=false;b.textContent='整理记录';}
  await loadEvents();
}
async function review(e){
  const b=$('reviewBtn');b.disabled=true;
  const x=await api('/api/events/'+e.record_id+'/review',{method:'POST',body:JSON.stringify({expected_version:e.version,action:'confirm',note:'仅确认记录准确'})});
  if(x.r.ok){toast('已记录“核对准确”');await loadEvents();await showDetail(e.record_id);}
  else {b.disabled=false;toast('核对未确认，请刷新后重试');}
}
function revise(e){$('subview').innerHTML=`<h3>修订记录</h3><textarea id="revText" rows="4">${escapeHtml(e.raw_text)}</textarea><input id="revReason" placeholder="修订原因（必填）" class="time-label"><button class="primary" id="submitRev">保存修订</button>`;$('submitRev').onclick=async()=>{const raw=$('revText').value.trim(),reason=$('revReason').value.trim();if(!raw||!reason){toast('请填写内容和修订原因');return}const x=await api('/api/events/'+e.record_id+'/revise',{method:'POST',body:JSON.stringify({raw_text:raw,source_kind:'elder',actor_name:'老人',expected_version:e.version,reason})});if(x.r.ok){toast('修订已保存');await loadEvents();showDetail(x.j.event.record_id)}else toast('修订失败，请重试')}}
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
function updateTimer(){const sec=Math.floor((Date.now()-startedAt)/1000);$('voiceTimer').textContent=`${String(Math.floor(sec/60)).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`}
function setRecording(on){$('recordBtn').classList.toggle('recording',on);$('recordBtn').querySelector('span').textContent=on?'正在说…':'开始说';$('finishVoiceBtn').disabled=!on;$('wave').classList.toggle('active',on)}
async function startVoice(){if(mediaRecorder?.state==='recording'||$('recordBtn').classList.contains('recording')){if(mediaRecorder?.state==='recording')mediaRecorder.stop();stopVoice('手动暂停');return}chunks=[];startedAt=Date.now();updateTimer();timerId=setInterval(updateTimer,1000);setRecording(true);$('voiceHint').textContent='正在听，请慢慢说';try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});mediaRecorder=new MediaRecorder(stream);mediaRecorder.ondataavailable=e=>chunks.push(e.data);mediaRecorder.onstop=()=>stream.getTracks().forEach(t=>t.stop());mediaRecorder.start()}catch(e){$('voiceHint').textContent='已进入演示模式，可以继续说；麦克风权限未开启';mediaRecorder=null}clearTimeout(silenceTimer);silenceTimer=setTimeout(()=>{if(mediaRecorder?.state==='recording'||$('recordBtn').classList.contains('recording')){$('voiceHint').textContent='好像停了一会儿';$('silenceNotice').classList.remove('hidden');if(mediaRecorder?.state==='recording')mediaRecorder.pause();setRecording(false)}},12000)}
function stopVoice(reason){clearInterval(timerId);clearTimeout(silenceTimer);if(mediaRecorder?.state==='recording'||mediaRecorder?.state==='paused')mediaRecorder.stop();mediaRecorder=null;setRecording(false);$('voiceHint').textContent=reason||'这一段已暂存';$('silenceNotice').classList.add('hidden')}
$('recordBtn').onclick=startVoice;$('finishVoiceBtn').onclick=()=>{stopVoice('这一段已暂存');toast('录音暂存在本页，等待媒体接口接入')};$('resumeBtn').onclick=()=>{if(mediaRecorder?.state==='paused')mediaRecorder.resume();$('silenceNotice').classList.add('hidden');setRecording(true);$('voiceHint').textContent='继续听，请慢慢说';silenceTimer=setTimeout(()=>{if(mediaRecorder?.state==='recording')mediaRecorder.pause();if($('recordBtn').classList.contains('recording')){setRecording(false);$('silenceNotice').classList.remove('hidden');$('voiceHint').textContent='好像停了一会儿'}},12000)};$('pauseBtn').onclick=()=>{stopVoice('已暂停，可以稍后重新开始')};$('saveBtn').onclick=save;$('refreshBtn').onclick=async()=>{await health();await loadEvents();toast('记录已刷新')};$('handoffBtn').onclick=handoff;
try {const pending=JSON.parse(localStorage.getItem(PENDING_SAVE_KEY)||'null');if(pending)$('rawText').value=JSON.parse(pending.body).raw_text;}catch{}
health().then(loadEvents);
