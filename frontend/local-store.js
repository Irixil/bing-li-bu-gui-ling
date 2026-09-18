(function () {
  'use strict';

  const core = globalThis.HealthLocalCore;
  const safety = globalThis.HealthSafety;
  if (!core || !safety || !globalThis.indexedDB) return;

  const driver = new core.IndexedDbDocumentStore();
  const vault = new core.EncryptedVault(driver);
  const SOURCE_KINDS = new Set(['elder', 'family_observation', 'family_report', 'caregiver', 'clinician_evidence', 'document', 'audio_transcript', 'system', 'unknown']);
  const MEDIA_TYPES = {
    audio: ['audio/aac', 'audio/flac', 'audio/m4a', 'audio/mp3', 'audio/mpeg', 'audio/mp4', 'audio/ogg', 'audio/wav', 'audio/webm', 'audio/x-m4a', 'audio/x-wav'],
    image: ['image/gif', 'image/jpeg', 'image/png', 'image/tiff', 'image/webp'],
  };
  const MAX_MEDIA_BYTES = 20 * 1024 * 1024;
  let initialisePromise;
  let active = false;

  function apiUrl(path) { return globalThis.BingliConfig?.apiUrl(path) || path; }

  function id(prefix) { return `${prefix}_${crypto.randomUUID().replaceAll('-', '')}`; }
  function now() { return new Date().toISOString(); }
  function ok(status, payload) { return { r: { ok: status >= 200 && status < 300, status }, j: payload }; }
  function fail(status, error, extra = {}) { return ok(status, { ok: false, error, ...extra }); }
  function parseBody(options) {
    if (!options?.body) return {};
    if (typeof options.body === 'string') return JSON.parse(options.body || '{}');
    return options.body;
  }
  function eventKey(recordId) { return `event:${recordId}`; }
  function mediaKey(mediaId) { return `media:${mediaId}`; }
  function mediaBinaryKey(mediaId) { return `media-binary:${mediaId}`; }

  function injectGate() {
    if (document.getElementById('localVaultGate')) return;
    const gate = document.createElement('section');
    gate.id = 'localVaultGate'; gate.className = 'secure-gate'; gate.setAttribute('role', 'dialog'); gate.setAttribute('aria-modal', 'true');
    gate.innerHTML = `<div class="secure-card"><div class="secure-brand"><img src="assets/brand-mascot.png" alt=""><div><strong>病历不归零·内测版</strong><span>你之前的完整前端已经在这里</span></div></div><p class="secure-kicker" id="vaultKicker">本机资料已加密</p><h1 id="vaultTitle">解锁本机健康资料</h1><p id="vaultExplain">健康记录加密保存在当前浏览器。恢复口令不会上传；忘记后无法由服务器找回。</p><form id="vaultForm"><label for="vaultPassphrase">恢复口令</label><input id="vaultPassphrase" type="password" minlength="10" autocomplete="current-password" required><label id="vaultConfirmLabel" for="vaultPassphraseConfirm" class="hidden">再输入一次</label><input id="vaultPassphraseConfirm" class="hidden" type="password" minlength="10" autocomplete="new-password"><button class="primary" id="vaultSubmit" type="submit">解锁</button><p id="vaultStatus" class="status" role="status"></p></form><p class="secure-foot">日常使用只需这一个本机口令。</p></div>`;
    document.body.append(gate);
  }

  async function unlockUi() {
    injectGate();
    const gate = document.getElementById('localVaultGate');
    const status = await vault.status();
    const isSetup = !status.configured;
    document.getElementById('vaultKicker').textContent = isSetup ? '第一次使用 · 只需设置一次' : '本机资料已加密';
    document.getElementById('vaultTitle').textContent = isSetup ? '为这台设备建立加密仓库' : '解锁本机健康资料';
    document.getElementById('vaultExplain').textContent = isSetup
      ? '设置完成后会马上进入完整首页。健康记录将加密保存在当前设备，恢复口令不会上传。'
      : '健康记录加密保存在当前浏览器。恢复口令不会上传；忘记后无法由服务器找回。';
    document.getElementById('vaultSubmit').textContent = isSetup ? '建立并进入' : '解锁';
    document.getElementById('vaultConfirmLabel').classList.toggle('hidden', !isSetup);
    document.getElementById('vaultPassphraseConfirm').classList.toggle('hidden', !isSetup);
    gate.classList.remove('hidden');
    return new Promise(resolve => {
      document.getElementById('vaultForm').onsubmit = async event => {
        event.preventDefault();
        const message = document.getElementById('vaultStatus');
        const button = document.getElementById('vaultSubmit');
        const passphrase = document.getElementById('vaultPassphrase').value;
        const confirmation = document.getElementById('vaultPassphraseConfirm').value;
        if (passphrase.length < 10) { message.textContent = '请使用至少 10 个字符的恢复口令。'; return; }
        if (isSetup && passphrase !== confirmation) { message.textContent = '两次输入不一致。'; return; }
        button.disabled = true; message.textContent = isSetup ? '正在建立加密仓库…' : '正在解锁…';
        try {
          if (isSetup) await vault.setup(passphrase); else await vault.unlock(passphrase);
          document.getElementById('vaultPassphrase').value = '';
          document.getElementById('vaultPassphraseConfirm').value = '';
          active = true; gate.classList.add('hidden');
          try { await navigator.storage?.persist?.(); } catch {}
          resolve(true);
        } catch {
          message.textContent = isSetup ? '建立失败，请确认浏览器允许本地存储。' : '口令不正确或本地数据已损坏。';
          button.disabled = false;
        }
      };
    });
  }

  async function initialise() {
    if (!initialisePromise) initialisePromise = unlockUi();
    await initialisePromise;
    return true;
  }

  async function cloudRequest(path, options = {}) {
    const headers = { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(options.headers || {}) };
    try {
      const response = await fetch(apiUrl(path), { ...options, credentials: 'include', headers });
      let body = {}; try { body = await response.json(); } catch {}
      return { r: response, j: body };
    } catch { return fail(0, 'network_unavailable'); }
  }

  async function listEvents() {
    const values = await vault.list('event:');
    return values.sort((a, b) => Date.parse(b.recorded_at) - Date.parse(a.recorded_at));
  }
  async function saveHistory(event, action, note = null) {
    await vault.put(`history:${event.record_id}:${Date.now()}:${crypto.randomUUID()}`, { action, at: now(), version: event.version, note, snapshot: event });
  }
  async function createEvent(body, idempotencyKey) {
    if (!body.raw_text?.trim()) return fail(400, 'raw_text_required');
    if (body.raw_text.length > 10000) return fail(400, 'raw_text_too_long');
    if (!SOURCE_KINDS.has(body.source_kind)) return fail(400, 'invalid_source_kind');
    if (idempotencyKey) {
      const replay = await vault.get(`operation:event:${idempotencyKey}`);
      if (replay) return ok(200, { ok: true, created: false, event: await vault.get(eventKey(replay.record_id)) });
    }
    const relatedRecordIds = Array.isArray(body.related_record_ids) ? [...new Set(body.related_record_ids.filter(value => typeof value === 'string' && value.startsWith('rec_')))].slice(-10) : [];
    const event = { record_id: id('rec'), raw_text: body.raw_text, source_kind: body.source_kind, actor_name: body.actor_name || '本地用户', occurred_time: body.occurred_time || null, recorded_at: now(), updated_at: now(), state: 'inbox', version: 1, local_safety: safety.scanDanger(body.raw_text), draft: null, related_record_ids: relatedRecordIds };
    await vault.put(eventKey(event.record_id), event); await saveHistory(event, 'created');
    if (idempotencyKey) await vault.put(`operation:event:${idempotencyKey}`, { record_id: event.record_id });
    return ok(201, { ok: true, created: true, event });
  }
  async function updateEvent(event, action, changes, note = null) {
    await saveHistory(event, action, note);
    const updated = { ...event, ...changes, version: event.version + 1, updated_at: now() };
    await vault.put(eventKey(event.record_id), updated); return updated;
  }

  async function eventRequest(path, options) {
    const method = options?.method || 'GET'; const parts = path.split('/').filter(Boolean); const body = parseBody(options);
    if (path === '/api/events' && method === 'GET') return ok(200, { ok: true, events: await listEvents() });
    if (path === '/api/events' && method === 'POST') return createEvent(body, options?.headers?.['Idempotency-Key']);
    const recordId = decodeURIComponent(parts[2] || ''); const event = await vault.get(eventKey(recordId));
    if (!event) return fail(404, 'event_not_found');
    if (parts.length === 3 && method === 'DELETE') {
      if (body.delete_scope_confirmed !== true) return fail(400, 'delete_confirmation_required');
      const linkedMedia = (await mediaList()).filter(item => item.event_link?.record_id === recordId || item.record_id === recordId);
      for (const item of linkedMedia) { await vault.remove(mediaBinaryKey(item.media_id)); await vault.remove(mediaKey(item.media_id)); }
      for (const history of await driver.listDocs(`history:${recordId}:`)) await vault.remove(history.key);
      await vault.remove(eventKey(recordId));
      return ok(200, { ok: true, deleted: { record_id: recordId, local_media_count: linkedMedia.length, encrypted_backups_unchanged: true } });
    }
    if (parts.length === 3 && method === 'GET') return ok(200, { ok: true, event });
    if (parts[3] === 'history' && method === 'GET') return ok(200, { ok: true, history: await vault.list(`history:${recordId}:`), audit: [] });
    if (method !== 'POST') return fail(404, 'not_found');
    if (Number(body.expected_version) !== event.version) return fail(409, 'stale_version');
    if (parts[3] === 'organize') {
      const related = (event.related_record_ids || []).map(item => vault.get(eventKey(item)));
      const history = (await Promise.all(related)).filter(Boolean).map(item => ({ record_id: item.record_id, raw_text: item.raw_text, source_kind: item.source_kind, recorded_at: item.recorded_at, occurred_time: item.occurred_time }));
      const result = await cloudRequest('/api/ai/organize', { method: 'POST', body: JSON.stringify({ record_id: event.record_id, raw_text: event.raw_text, source_kind: event.source_kind, recorded_at: event.recorded_at, occurred_time: event.occurred_time, history }) });
      if (!result.r.ok) return ok(result.r.status || 422, { ...result.j, event, local_safety: event.local_safety });
      const updated = await updateEvent(event, 'organized', { state: 'draft', draft: result.j.output, local_safety: event.local_safety, ai_metadata: { provider: result.j.provider, model_id: result.j.model_id, prompt_version: result.j.prompt_version, trace_id: result.j.trace_id } });
      return ok(200, { ok: true, event: updated, ...result.j });
    }
    if (parts[3] === 'review') {
      const state = body.action === 'reject' ? 'needs_review' : 'recorded';
      const updated = await updateEvent(event, 'reviewed', { state, confirmation_scope: state === 'recorded' ? 'record_accuracy' : null }, body.note || null);
      return ok(200, { ok: true, event: updated });
    }
    if (parts[3] === 'revise') {
      if (!body.raw_text?.trim() || !body.reason?.trim()) return fail(400, 'revision_fields_required');
      const superseded = await updateEvent(event, 'superseded', { state: 'superseded' }, body.reason);
      const replacement = { ...superseded, record_id: id('rec'), raw_text: body.raw_text, source_kind: body.source_kind || event.source_kind, actor_name: body.actor_name || event.actor_name, recorded_at: now(), updated_at: now(), occurred_time: event.occurred_time, state: 'inbox', version: 1, supersedes_id: event.record_id, local_safety: safety.scanDanger(body.raw_text), draft: null, ai_metadata: null };
      await vault.put(eventKey(replacement.record_id), replacement); await saveHistory(replacement, 'created_from_revision', body.reason);
      return ok(201, { ok: true, event: replacement });
    }
    return fail(404, 'not_found');
  }

  function mediaPublic(media) { return { ...media }; }
  async function mediaList() { return (await vault.list('media:')).filter(item => item?.media_id).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)); }
  function mediaCapabilities() { return { enabled: true, disabled_reason: null, max_total_bytes: MAX_MEDIA_BYTES, max_part_bytes: 2 * 1024 * 1024, max_parts: 12, audio_content_types: MEDIA_TYPES.audio, image_content_types: MEDIA_TYPES.image, multipart_upload: true, resumable_parts: true }; }
  async function mediaRequest(path, options) {
    const method = options?.method || 'GET'; const parts = path.split('/').filter(Boolean);
    if (path === '/api/media/capabilities' && method === 'GET') return ok(200, { ok: true, capabilities: mediaCapabilities() });
    if (path === '/api/media' && method === 'GET') return ok(200, { ok: true, media: (await mediaList()).map(mediaPublic) });
    if (path === '/api/media/uploads' && method === 'POST') {
      const form = parseBody(options); const kind = form.get('kind'); const type = String(form.get('content_type') || '').split(';')[0]; const totalParts = Number(form.get('total_parts'));
      if (!MEDIA_TYPES[kind]?.includes(type) || !Number.isInteger(totalParts) || totalParts < 1 || totalParts > 12) return fail(415, 'unsupported_format');
      const operationKey=options?.headers?.['Idempotency-Key'];
      if(operationKey){const replay=await vault.get(`operation:media-upload:${operationKey}`);if(replay){const existing=await vault.get(`upload:${replay.upload_id}`);if(existing)return ok(200,{ok:true,created:false,upload:existing});}}
      const uploadId = id('upload'); const mediaId = id('media');
      const upload = { upload_id: uploadId, media_id: mediaId, kind, content_type: type, total_parts: totalParts, expected_size: Number(form.get('expected_size')), expected_sha256: form.get('expected_sha256'), original_filename: form.get('original_filename') || 'media', created_at: now() };
      await vault.put(`upload:${uploadId}`, upload);if(operationKey)await vault.put(`operation:media-upload:${operationKey}`,{upload_id:uploadId,media_id:mediaId});return ok(201, { ok: true, created: true, upload });
    }
    if (parts[0] === 'api' && parts[1] === 'media' && parts[2] === 'uploads' && parts[4] === 'parts' && method === 'POST') {
      const upload = await vault.get(`upload:${parts[3]}`); if (!upload) return fail(404, 'upload_not_found');
      const index = Number(parts[5]); const file = parseBody(options).get('file');
      if (!Number.isInteger(index) || index < 0 || index >= upload.total_parts || !file) return fail(400, 'invalid_part');
      await vault.putBinary(`upload-part:${upload.upload_id}:${String(index).padStart(3, '0')}`, file, { index, size: file.size });
      return ok(201, { ok: true, created: true, part: { index, size: file.size } });
    }
    if (parts[0] === 'api' && parts[1] === 'media' && parts[2] === 'uploads' && parts[4] === 'complete' && method === 'POST') {
      const upload = await vault.get(`upload:${parts[3]}`); if (!upload) return fail(404, 'upload_not_found');
      const chunks = [];
      for (let index = 0; index < upload.total_parts; index += 1) {
        const item = await vault.get(`upload-part:${upload.upload_id}:${String(index).padStart(3, '0')}`); if (!item) return fail(409, 'upload_incomplete'); chunks.push(new Uint8Array(item.bytes));
      }
      const size = chunks.reduce((sum, item) => sum + item.length, 0); if (!size || size > MAX_MEDIA_BYTES || size !== upload.expected_size) return fail(422, 'integrity_mismatch');
      const bytes = new Uint8Array(size); let offset = 0; for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(value => value.toString(16).padStart(2, '0')).join('');
      if (upload.expected_sha256 && digest !== upload.expected_sha256) return fail(422, 'integrity_mismatch');
      const media = { media_id: upload.media_id, kind: upload.kind, content_type: upload.content_type, original_filename: upload.original_filename, size, sha256: digest, created_at: now(), updated_at: now(), save_status: 'saved', recognition_status: 'not_started', link_status: 'not_linked', version: 1, recognition: null, event_link: null, local_safety: null };
      await vault.putBinary(mediaBinaryKey(media.media_id), bytes.buffer, { content_type: media.content_type, filename: media.original_filename }); await vault.put(mediaKey(media.media_id), media);
      for (let index = 0; index < upload.total_parts; index += 1) await vault.remove(`upload-part:${upload.upload_id}:${String(index).padStart(3, '0')}`);
      await vault.remove(`upload:${upload.upload_id}`); return ok(201, { ok: true, created: true, media: mediaPublic(media) });
    }
    const mediaId = parts[2]; let media = await vault.get(mediaKey(mediaId));
    if(!media&&parts.length===3&&method==='GET'){const upload=(await vault.list('upload:')).find(item=>item.media_id===mediaId);if(upload)return ok(200,{ok:true,media:{media_id:mediaId,kind:upload.kind,content_type:upload.content_type,original_filename:upload.original_filename,save_status:'uploading',recognition_status:'not_started',link_status:'not_linked',version:0}})}
    if (!media) return fail(404, 'media_not_found');
    if (parts.length === 3 && method === 'GET') return ok(200, { ok: true, media: mediaPublic(media) });
    if (parts[3] === 'recognize' && method === 'POST') {
      if (media.recognition_status === 'processing') return ok(202, { ok: true, action: 'existing', media: mediaPublic(media) });
      const processing = { ...media, recognition_status: 'processing', version: media.version + 1, updated_at: now(), recognition: null };
      await vault.put(mediaKey(mediaId), processing); processRecognition(processing); return ok(202, { ok: true, action: 'started', media: mediaPublic(processing) });
    }
    if (parts[3] === 'link' && method === 'POST') {
      if (media.recognition_status !== 'succeeded' || !media.recognition?.text) return fail(409, 'recognition_not_succeeded');
      if (media.event_link?.record_id) return ok(200, { ok: true, event_created: false, media: mediaPublic(media) });
      const created = await createEvent({ raw_text: media.recognition.text, source_kind: media.kind === 'audio' ? 'audio_transcript' : 'document', actor_name: '本地用户' }, `media-link:${mediaId}`);
      const linked = { ...media, event_link: { record_id: created.j.event.record_id }, record_id: created.j.event.record_id, link_status: 'linked', version: media.version + 1, updated_at: now(), local_safety: created.j.event.local_safety };
      await vault.put(mediaKey(mediaId), linked); return ok(201, { ok: true, event_created: true, media: mediaPublic(linked), event: created.j.event });
    }
    return fail(404, 'not_found');
  }

  async function processRecognition(media) {
    try {
      const original = await vault.get(mediaBinaryKey(media.media_id));
      const form = new FormData(); form.append('kind', media.kind); form.append('content_type', media.content_type); form.append('attempt_id', id('attempt')); form.append('file', new Blob([original.bytes], { type: media.content_type }), media.original_filename);
      const result = await cloudRequest('/api/ai/media/recognize', { method: 'POST', body: form });
      if (!result.r.ok) throw Object.assign(new Error(result.j.error || 'recognition_failed'), { code: result.j.error, retryable: result.j.retryable === true });
      const created = await createEvent({ raw_text: result.j.recognition.text, source_kind: media.kind === 'audio' ? 'audio_transcript' : 'document', actor_name: '本地用户' }, `media-link:${media.media_id}`);
      const updated = { ...media, recognition_status: 'succeeded', recognition: result.j.recognition, local_safety: created.j.event.local_safety, event_link: { record_id: created.j.event.record_id }, record_id: created.j.event.record_id, link_status: 'linked', version: media.version + 1, updated_at: now() };
      await vault.put(mediaKey(media.media_id), updated);
    } catch (error) {
      const retryable = error.retryable === true || ['network_unavailable', 'provider_timeout', 'provider_unavailable', 'provider_rate_limited'].includes(error.code);
      const updated = { ...media, recognition_status: 'failed', recognition: { error_message: retryable ? '识别没有完成，原件已保存在本机，可以重试。' : '识别没有完成，原件已保存在本机。', error: { code: error.code || 'recognition_failed', retryable }, retryable }, version: media.version + 1, updated_at: now() };
      await vault.put(mediaKey(media.media_id), updated);
    }
  }

  async function request(path, options = {}) {
    try {
      await initialise();
      if (path === '/api/handoffs' && (options.method || 'GET') === 'POST') {
        const body=parseBody(options),start=body.start_date?Date.parse(`${body.start_date}T00:00:00`):null,end=body.end_date?Date.parse(`${body.end_date}T23:59:59.999`):null;
        const selected=Array.isArray(body.record_ids)?new Set(body.record_ids):null;
        const items = (await listEvents()).filter(event => event.state !== 'superseded').filter(event=>{const at=Date.parse(event.recorded_at);return (!selected||selected.has(event.record_id))&&(!start||at>=start)&&(!end||at<=end)}); const media = await mediaList();
        return ok(201, { ok: true, handoff: { handoff_id: id('handoff'), created_at: now(), items: items.map(event => ({ ...event, unresolved: event.state !== 'recorded' || event.local_safety?.danger_detected || event.local_safety?.clinical_review_required })), media_attachments: media.map(item => ({ ...item, unresolved: item.recognition_status !== 'succeeded' || item.link_status !== 'linked' })), unresolved_count: items.filter(event => event.state !== 'recorded' || event.local_safety?.danger_detected || event.local_safety?.clinical_review_required).length + media.filter(item => item.recognition_status !== 'succeeded' || item.link_status !== 'linked').length } });
      }
      if (path.startsWith('/api/events')) return eventRequest(path, options);
      if (path.startsWith('/api/media')) return mediaRequest(path, options);
      return fail(404, 'not_found');
    } catch (error) { return fail(400, error.message || 'local_request_failed'); }
  }

  async function originalObjectUrl(mediaId) {
    await initialise(); const original = await vault.get(mediaBinaryKey(mediaId)); if (!original) throw new Error('原件不存在');
    return URL.createObjectURL(new Blob([original.bytes], { type: original.metadata.content_type || 'application/octet-stream' }));
  }

  async function backupBlob() {
    await initialise(); const archive = await vault.exportArchive();
    return new Blob([JSON.stringify(archive)], { type: 'application/vnd.bingli.encrypted+json' });
  }

  async function downloadBackup() {
    const blob = await backupBlob();
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `病历不归零-加密备份-${new Date().toISOString().slice(0, 10)}.bingli`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function previewBackup(file, passphrase) {
    await initialise();
    if (!file || file.size > 100 * 1024 * 1024) throw new Error('backup_too_large');
    let archive; try { archive = JSON.parse(await file.text()); } catch { throw new Error('invalid_backup'); }
    const preview = await vault.previewArchive(archive, passphrase);
    return { archive, eventCount: preview.eventCount, mediaCount: preview.mediaCount, exportedAt: preview.exportedAt };
  }

  async function restoreBackup(preview, passphrase) {
    if (!preview?.archive) throw new Error('backup_not_previewed');
    return vault.restoreArchive(preview.archive, passphrase);
  }

  async function saveFeedback(description, page) {
    await initialise();
    if (typeof description !== 'string' || !description.trim() || description.length > 2000) throw new Error('feedback_invalid');
    const feedback = { feedback_id: id('feedback'), description: description.trim(), page: String(page || location.hash || 'home').slice(0, 120), occurred_at: now(), includes_health_content: false, status: 'saved_on_device' };
    await vault.put(`feedback:${feedback.feedback_id}`, feedback); return feedback;
  }

  async function storageStatus() {
    const estimate = await navigator.storage?.estimate?.();
    return { persisted: await navigator.storage?.persisted?.(), usage: estimate?.usage || 0, quota: estimate?.quota || 0 };
  }

  globalThis.HealthLocal = {
    get active() { return active; },
    downloadBackup,
    initialise,
    lock() { vault.lock(); active = false; initialisePromise = null; },
    originalObjectUrl,
    previewBackup,
    request,
    restoreBackup,
    saveFeedback,
    storageStatus,
    vault,
  };
})();
