// P0 saved-media upload and recognition; no change to the VAD algorithm.
let mediaItems=[], uploadBusy=false, selectedPhoto=null, pendingRecordingBlob=null, mediaCapabilities=null;
const localMediaJobs=new Map();
const recognitionBusy=new Set();
const originalUrls=new Map();
const mediaStatus=$('mediaStatus');
const mediaLabel=m=>`${m.kind==='audio'?'录音':'照片'} · 原件${m.save_status==='saved'?'已保存':'尚未保存完整'} · ${({not_started:'待识别',processing:'识别处理中',succeeded:'文字已识别，待核对',failed:'识别失败',interrupted:'识别中断'})[m.recognition_status]||m.recognition_status}`;
function mediaMessage(text){mediaStatus.textContent=text;}
function mediaRetryable(m){
  // The API puts retryability on the current attempt's error.  Accept the
  // compatibility locations too, but never infer that a terminal failure is
  // retryable merely because it has a failed status.
  if(m?.recognition_status==='interrupted')return m.recognition?.retryable!==false;
  if(m?.recognition_status!=='failed')return false;
  return m.recognition?.retryable===true||m.recognition?.error?.retryable===true||m.retryable===true;
}
function capabilityMessage(c){
  if(c?.enabled===true)return '';
  if(c?.disabled_reason==='media_limits_not_configured')return '当前实例未配置媒体资源保护边界，媒体上传暂不可用。';
  return '媒体上传能力暂不可用，请检查服务配置后刷新。';
}
function setMediaCapability(c){
  mediaCapabilities=c||null;
  const disabled=!c||c.enabled!==true;
  const status=$('mediaCapabilityStatus');if(status){status.textContent=capabilityMessage(c);status.classList.toggle('error',disabled);}
  const photoStatus=$('photoCapabilityStatus');if(photoStatus){photoStatus.textContent=capabilityMessage(c);photoStatus.classList.toggle('error',disabled);}
  for(const id of ['photoInput','audioUploadInput','savePhotoBtn']){
    const el=$(id);if(el)el.disabled=disabled;
  }
  for(const id of ['photoUploadLabel','audioUploadLabel']){
    const el=$(id);if(!el)continue;
    el.setAttribute?.('aria-disabled',String(disabled));
    el.classList.toggle('media-disabled',disabled);
  }
  document.querySelectorAll('[data-media-entry]').forEach(el=>{
    el.disabled=disabled;
    el.setAttribute?.('aria-disabled',String(disabled));
  });
  if(disabled){
    selectedPhoto=null;
    $('photoPreview')?.classList.add('hidden');
    $('savePhotoBtn')?.classList.add('hidden');
  }
  return !disabled;
}
async function loadMediaCapabilities(){
  try{
    const {r,j}=await api('/api/media/capabilities');
    if(!r.ok||!j.capabilities){
      setMediaCapability(null);
      return false;
    }
    return setMediaCapability(j.capabilities);
  }catch{
    // Capability discovery is advisory for an already rendered archive. A
    // transient read failure must not create an unhandled rejection; upload
    // still performs a mandatory, authoritative capability check.
    setMediaCapability(null);
    return false;
  }
}
async function mediaRequest(path,opt){
  const x=await api(path,opt);
  if(!x.r.ok)throw new Error(x.r.status===0?'连接中断，请重试，原文件和重试信息保留':x.j.error||'媒体请求失败');
  return x.j;
}
async function loadMedia(){
  const {r,j}=await api('/api/media');
  if(!r.ok){mediaMessage('媒体列表暂时无法读取，请恢复连接后刷新');return;}
  mediaItems=j.media||[];renderMedia();
}
function renderMedia(){
  $('archivePhotoCount').textContent=mediaItems.filter(m=>m.kind==='image'&&m.save_status==='saved').length;
  $('archivePhotos').innerHTML=mediaItems.length?latestMediaFirst(mediaItems).map(m=>{
    const terminalUnavailable=['failed','interrupted'].includes(m.recognition_status)&&!mediaRetryable(m);
    const action=m.recognition_status==='succeeded'?'查看识别文字':m.recognition_status==='processing'?'识别处理中':terminalUnavailable?'':'识别 / 重试';
    const actionButton=action?`<button class="outline" data-recognize="${m.media_id}" ${m.save_status!=='saved'||m.recognition_status==='processing'?'disabled':''}>${action}</button>`:'';
    return `<article class="handoff-item" id="media-${m.media_id}"><b>${escapeHtml(m.original_filename||'媒体原件')}</b><p>${mediaLabel(m)}</p>${m.recognition?.is_mock?'<p class="status error">离线 Mock 演示模式：文字不是原件的真实识别结果</p>':''}${m.recognition?.error_message?`<p class="status error">${escapeHtml(m.recognition.error_message)}</p>`:''}${terminalUnavailable?'<p class="status error">该识别失败不可重试，原件仍可查看。</p>':''}<button class="outline" data-original="${m.media_id}" ${m.save_status!=='saved'?'disabled':''}>查看原件</button>${actionButton}<div class="media-result"></div></article>`;
  }).join(''):'<p class="muted">还没有上传原件</p>';
  document.querySelectorAll('[data-original]').forEach(b=>b.onclick=()=>openOriginal(b.dataset.original));
  document.querySelectorAll('[data-recognize]').forEach(b=>b.onclick=()=>recognizeMedia(b.dataset.recognize));
}
function latestMediaFirst(items){return items.slice().sort((a,b)=>{const at=Date.parse(a.created_at||a.updated_at||'')||0;const bt=Date.parse(b.created_at||b.updated_at||'')||0;return bt-at||String(b.media_id||'').localeCompare(String(a.media_id||''))})}
async function openOriginal(id){
  try{
    if(originalUrls.has(id))URL.revokeObjectURL(originalUrls.get(id));
    let url;
    if(globalThis.HealthLocal?.active)url=await globalThis.HealthLocal.originalObjectUrl(id);
    else{await health();const r=await fetch(API+`/api/media/${id}/original`,{credentials:'include',headers:{'X-Session-Token':token}});if(!r.ok)throw new Error('原件暂时无法读取');url=URL.createObjectURL(await r.blob());}
    originalUrls.set(id,url);
    const m=mediaItems.find(m=>m.media_id===id);const box=$('media-'+id).querySelector('.media-result');
    const node=document.createElement(m.kind==='audio'?'audio':'img');node.src=url;
    if(m.kind==='audio')node.controls=true;else{node.alt='已保存的照片原件';node.style.maxWidth='100%';}
    box.replaceChildren(node);
  }catch(e){mediaMessage(e.message);}
}
async function uploadMedia(file,kind){
  if(uploadBusy)return;
  uploadBusy=true;
  try{
    if(!await health())throw new Error('服务未连接，文件仍在本页，请重试');
    const {capabilities:c}=await mediaRequest('/api/media/capabilities');
    setMediaCapability(c);
    if(!c.enabled)throw new Error('当前实例未配置媒体资源保护边界，请负责人按启动说明配置');
    const type=(file.type||'').split(';')[0];
    if(!(kind==='audio'?c.audio_content_types:c.image_content_types).includes(type))throw new Error('当前服务不支持该文件格式，请保留原件并换用支持的格式');
    if(!file.size||file.size>c.max_total_bytes)throw new Error('文件为空或超过当前实例的资源保护边界');
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer())),v=>v.toString(16).padStart(2,'0')).join('');
    const jobKey=`elder_media_upload_v1:${kind}:${hash}:${type}`;
    let job;if(globalThis.HealthLocal?.active)job=localMediaJobs.get(jobKey);else try{job=JSON.parse(localStorage.getItem(jobKey)||'null')}catch{}
    if(!job){
      const chunkSize=c.max_part_bytes,total=Math.ceil(file.size/chunkSize);
      if(total>c.max_parts)throw new Error('文件分片数量超过当前实例边界');
      job={key:crypto.randomUUID(),chunkSize,metadata:{kind,content_type:type,total_parts:String(total),expected_size:String(file.size),expected_sha256:hash,original_filename:file.name||`recording.${type.split('/')[1]}`,actor_name:'老人'}};
      if(globalThis.HealthLocal?.active)localMediaJobs.set(jobKey,job);else localStorage.setItem(jobKey,JSON.stringify(job));
    }
    if(job.mediaId){
      const {media}=await mediaRequest('/api/media/'+job.mediaId);
      if(media.save_status==='saved'){mediaMessage('原件已经保存，重复提交已复用同一条媒体');await loadMedia();return media;}
    }
    mediaMessage('正在创建上传，原件尚未保存完整');
    const form=new FormData();Object.entries(job.metadata).forEach(([k,v])=>form.append(k,v));
    const {upload}=await mediaRequest('/api/media/uploads',{method:'POST',headers:{'Idempotency-Key':job.key+':create'},body:form});
    job.mediaId=upload.media_id;job.uploadId=upload.upload_id;if(globalThis.HealthLocal?.active)localMediaJobs.set(jobKey,job);else localStorage.setItem(jobKey,JSON.stringify(job));
    for(let i=0;i<Number(job.metadata.total_parts);i++){
      mediaMessage(`正在上传 ${i+1}/${job.metadata.total_parts}，原件尚未保存完整`);
      const part=new FormData();part.append('file',file.slice(i*job.chunkSize,(i+1)*job.chunkSize),`part-${i}`);
      await mediaRequest(`/api/media/uploads/${job.uploadId}/parts/${i}`,{method:'POST',headers:{'Idempotency-Key':job.key+':part:'+i},body:part});
    }
    const {media}=await mediaRequest(`/api/media/uploads/${job.uploadId}/complete`,{method:'POST',headers:{'Idempotency-Key':job.key+':complete'},body:'{}'});
    if(media.save_status!=='saved')throw new Error('原件尚未确认保存，请重试');
    mediaMessage('原件已保存。请在看病资料中识别并核对文字');await loadMedia();return media;
  }catch(e){mediaMessage(e.message);toast(e.message);}
  finally{uploadBusy=false;}
}
function showRecognition(m){
  const box=$('media-'+m.media_id)?.querySelector('.media-result');if(!box)return;
  box.innerHTML=(m.recognition?.is_mock?'<p class="status error">离线 Mock 演示模式：不代表真实识别</p>':'')+safetyHtml(m.local_safety||m.recognition?.local_safety)+`<div class="raw-box">${escapeHtml(m.recognition?.text||m.recognition?.error_message||'没有可用识别文字；原件保留')}</div>`;
  const rid=m.event_link?.record_id||m.record_id;
  if(rid){const b=document.createElement('button');b.className='primary';b.textContent='核对识别记录';b.onclick=()=>{showView('recordsView');showDetail(rid)};box.append(b);}
  else if(m.recognition_status==='succeeded'){
    const b=document.createElement('button');b.className='outline';b.textContent=globalThis.HealthLocal?.active?'把识别文字保存为待核对记录':'恢复记录关联';
    b.onclick=async()=>{b.disabled=true;try{const {media:latest}=await mediaRequest('/api/media/'+m.media_id);await mediaRequest(`/api/media/${m.media_id}/link`,{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({expected_version:latest.version})});await loadMedia();const {media}=await mediaRequest('/api/media/'+m.media_id);showRecognition(media);await loadEvents();}catch(e){mediaMessage(e.message);b.disabled=false;}};box.append(b);
  }
}
function recognitionStillFinishing(m){
  return m.recognition_status==='processing'||(m.recognition_status==='succeeded'&&!m.event_link?.record_id&&!m.record_id&&['safety_scan_pending','event_link_pending'].includes(m.link_pending_reason));
}
async function recognizeMedia(id){
  if(recognitionBusy.has(id))return;
  recognitionBusy.add(id);
  try{
    let {media:m}=await mediaRequest('/api/media/'+id);
    if(['failed','interrupted'].includes(m.recognition_status)&&!mediaRetryable(m)){
      showRecognition(m);
      mediaMessage('该识别失败不可重试；原件仍可查看');
      return;
    }
    if(m.recognition_status==='succeeded'&&!recognitionStillFinishing(m)){showRecognition(m);return;}
    if(!['processing','succeeded'].includes(m.recognition_status)){
      const opKey='elder_media_recognize_v1:'+id;
      let op;try{op=JSON.parse(localStorage.getItem(opKey)||'null')}catch{}
      // Reuse uncertain submissions. A terminal failure needs a new attempt/version.
      if(!op||op.version!==m.version)op={key:crypto.randomUUID(),version:m.version};
      localStorage.setItem(opKey,JSON.stringify(op));
      await mediaRequest(`/api/media/${id}/recognize`,{method:'POST',headers:{'Idempotency-Key':op.key},body:JSON.stringify({expected_version:op.version})});
    }
    mediaMessage('识别处理中；原件已保存，可以稍后刷新查看');await loadMedia();
    for(let i=0;i<120;i++){
      const {media}=await mediaRequest('/api/media/'+id);
      if(!recognitionStillFinishing(media)){
        await loadMedia();showRecognition(media);await loadEvents();
        mediaMessage(media.recognition_status==='succeeded'?'识别文字已保留，请核对来源和内容':'识别失败或中断，原件仍可查看和重试');return;
      }
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
    await loadMedia();
    const {media}=await mediaRequest('/api/media/'+id);showRecognition(media);
    mediaMessage('识别或记录关联仍待完成，请稍后刷新或恢复关联；原件已保存');
  }catch(e){mediaMessage(e.message);await loadMedia();}
  finally{recognitionBusy.delete(id);}
}
$('photoInput').onchange=e=>{
  if(mediaCapabilities&&mediaCapabilities.enabled!==true)return;
  selectedPhoto=e.target.files?.[0];if(!selectedPhoto)return;
  // Clearing the value after capturing the File permits selecting the same
  // path again after a failed upload (the browser otherwise suppresses the
  // second `change` event).
  e.target.value='';
  const preview=$('photoPreview');preview.replaceChildren();const img=document.createElement('img');
  img.src=URL.createObjectURL(selectedPhoto);img.alt='待上传照片预览';img.onload=()=>URL.revokeObjectURL(img.src);preview.append(img);
  const note=document.createElement('p');note.textContent='仅预览，尚未上传或识别';preview.append(note);preview.classList.remove('hidden');$('savePhotoBtn').classList.remove('hidden');
};
$('savePhotoBtn').onclick=async()=>{if(uploadBusy)return;const m=await uploadMedia(selectedPhoto,'image');if(m){showView('archiveView');}};
$('audioUploadInput').onchange=async e=>{if(mediaCapabilities&&mediaCapabilities.enabled!==true)return;const f=e.target.files?.[0];e.target.value='';if(f){await uploadMedia(f,'audio');showView('archiveView');}};
async function savePendingRecording(){
  if(!pendingRecordingBlob||uploadBusy)return;
  const retry=$('retryVoiceUploadBtn');retry.disabled=true;
  const media=await uploadMedia(pendingRecordingBlob,'audio');
  if(media){
    pendingRecordingBlob=null;voiceUploadPending=false;setRecording(false);
    retry.classList.add('hidden');$('voiceHint').textContent='原件已保存，可在看病资料核对识别文字';
    if(!globalThis.HealthLocal?.active)await recognizeMedia(media.media_id);
  }else{
    // A non-retryable capability/provider failure cannot be fixed by clicking
    // this button.  Keep the original in memory, but avoid presenting a
    // misleading retry affordance.
    const retryable=mediaCapabilities?.enabled!==false;
    retry.classList.toggle('hidden',!retryable);
    $('voiceHint').textContent=retryable?'录音尚未保存，请到看病资料重试上传，先不要刷新或关闭页面':'录音尚未保存；当前媒体能力不可用，请恢复配置后再试';
  }
  retry.disabled=false;
}
// Capture this recorder's array before a later recording can replace globals.
$('finishVoiceBtn').onclick=()=>{
  if(voiceUploadPending||voicePermissionPending)return;
  const recorder=mediaRecorder;
  if(!recorder||recorder.state==='inactive'){stopVoice('没有可上传录音，请先开启麦克风或上传已有录音');return;}
  const recordingChunks=chunks;
  voiceUploadPending=true;
  recorder.addEventListener('stop',async()=>{
    const blob=new Blob(recordingChunks,{type:recorder.mimeType});
    showView('archiveView');
    if(blob.size){
      pendingRecordingBlob=blob;
      $('retryVoiceUploadBtn').classList.remove('hidden');
      await savePendingRecording();
    }
    else {voiceUploadPending=false;setRecording(false);mediaMessage('未取得录音字节，请检查麦克风或上传已有录音');}
  },{once:true});
  stopVoice('正在保留这一段录音');
};
$('retryVoiceUploadBtn').onclick=savePendingRecording;
window.addEventListener('beforeunload',e=>{if(voiceUploadPending){e.preventDefault();e.returnValue='';}});
$('refreshMediaBtn').onclick=async()=>{await health();await loadMediaCapabilities();await loadMedia();};
document.querySelectorAll('[data-view="archiveView"]').forEach(b=>b.addEventListener('click',async()=>{await loadMediaCapabilities();await loadMedia();}));
setMediaCapability(null);
health().then(async()=>{await loadMediaCapabilities();await loadMedia();});
