// Controlled browser/API state regression. This is not real microphone or ASR evidence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto, randomUUID } = require('node:crypto');
const { test } = require('node:test');

function harness() {
  const elements = new Map(), storage = new Map(), recorders = [], views = [], requests = [], windowListeners = {};
  let response = async () => ({ r: { ok: true, status: 200 }, j: { ok: true, media: [] } });
  let nextId = 1, waits = 0;
  function element(id) {
    if (!elements.has(id)) {
      const classes = new Set();
      elements.set(id, {
        id, value: '', textContent: '', innerHTML: '', disabled: false, dataset: {}, style: {}, children: [],
        classList: {
          add(name) { classes.add(name); }, remove(name) { classes.delete(name); }, contains(name) { return classes.has(name); },
          toggle(name, on) { if (on ?? !classes.has(name)) classes.add(name); else classes.delete(name); },
        },
        querySelector(selector) { return element(id + ':' + selector); }, querySelectorAll() { return []; },
        addEventListener() {}, scrollIntoView() {}, append(child) { this.children.push(child); },
        replaceChildren(...children) { this.children = children; },
      });
    }
    return elements.get(id);
  }
  class Recorder {
    constructor(stream) { this.stream = stream; this.state = 'inactive'; this.mimeType = 'audio/webm'; this.listeners = []; recorders.push(this); }
    start() { this.state = 'recording'; }
    pause() { this.state = 'paused'; }
    resume() { this.state = 'recording'; }
    stop() { this.state = 'inactive'; }
    addEventListener(name, callback) { assert.equal(name, 'stop'); this.listeners.push(callback); }
    emit(text) { this.ondataavailable?.({ data: new Blob([text], { type: this.mimeType }) }); }
    async finish(finalText = '') {
      if (finalText) this.emit(finalText);
      this.onstop?.();
      for (const listener of this.listeners.splice(0)) await listener();
    }
  }
  const context = vm.createContext({
    console, Blob, FormData, URL, crypto: { subtle: webcrypto.subtle, randomUUID }, MediaRecorder: Recorder,
    location: { hostname: 'localhost', port: '5173' },
    navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) } },
    document: { getElementById: element, querySelectorAll: () => [], createElement: tag => element('new-' + tag + nextId++) },
    window: { scrollTo() {}, addEventListener(name, callback) { windowListeners[name] = callback; } },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true, session_token: 'test', provider: 'mock', events: [] }) }),
    setInterval() { return nextId++; }, clearInterval() {}, clearTimeout() {},
    setTimeout(callback, milliseconds) { if (milliseconds === 1000) { waits++; queueMicrotask(callback); } return nextId++; },
  });
  function run(code) { return vm.runInContext(code, context); }
  run(fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8'));
  context.testApi = async (route, options = {}) => {
    requests.push({ route, options });
    if (route === '/api/events') return { r: { ok: true }, j: { events: [] } };
    return response(route, options);
  };
  context.testShowView = id => views.push(id);
  run('api=testApi; health=async()=>true; loadEvents=async()=>{}; showView=testShowView; toast=()=>{};');
  run(fs.readFileSync(path.join(__dirname, '../frontend/media.js'), 'utf8'));
  return {
    element, recorders, views, requests, storage, windowListeners, run, context,
    click: id => element(id).onclick(), setApi(callback) { response = callback; },
    get waits() { return waits; },
  };
}

const saved = () => ({ media_id: 'media_test', kind: 'audio', content_type: 'audio/webm',
  version: 1, save_status: 'saved', recognition_status: 'not_started', link_status: 'not_linked' });

test('finish captures this recorder and final bytes even if the global chunks array changes', async () => {
  const h = harness();
  let captured;
  h.context.captureUpload = async blob => { captured = blob; return null; };
  h.run('uploadMedia=captureUpload');
  await h.click('recordBtn');
  h.recorders[0].emit('before-pause/');
  await h.click('pauseBtn');
  await h.click('resumeBtn');
  h.recorders[0].emit('after-resume/');
  h.click('finishVoiceBtn');
  assert.equal(h.run('voiceUploadPending'), true);
  assert.equal(h.element('recordBtn').disabled, true);
  h.run('chunks=[]');
  await h.recorders[0].finish('final-stop-data');
  assert.equal(await captured.text(), 'before-pause/after-resume/final-stop-data');
  assert.equal(await h.run('pendingRecordingBlob').text(), await captured.text());
  assert.equal(h.element('retryVoiceUploadBtn').classList.contains('hidden'), false);
  assert.equal(h.views.length, 0, '完整前端应留在语音对话里展示保存和识别状态');
});

test('failed multipart upload keeps original Blob and retry identity; success automatically recognizes', async () => {
  const h = harness();
  const media = saved();
  let failPart = true, recognizeCount = 0;
  const partKeys = [], partBytes = [];
  h.setApi(async (route, options) => {
    if (route === '/api/media') return { r: { ok: true, status: 200 }, j: { media: [media] } };
    if (route === '/api/media/capabilities') return { r: { ok: true }, j: { capabilities: {
      enabled: true, audio_content_types: ['audio/webm'], image_content_types: ['image/png'],
      max_total_bytes: 1000, max_part_bytes: 1000, max_parts: 2,
    } } };
    if (route === '/api/media/uploads') return { r: { ok: true }, j: { upload: { media_id: 'media_test', upload_id: 'upload_test' } } };
    if (route === '/api/media/media_test') return { r: { ok: true }, j: { media: { ...media, save_status: 'uploading' } } };
    if (route === '/api/media/uploads/upload_test/parts/0') {
      partKeys.push(options.headers['Idempotency-Key']); partBytes.push(await options.body.get('file').text());
      if (failPart) return { r: { ok: false, status: 0 }, j: {} };
      return { r: { ok: true }, j: { created: true } };
    }
    if (route === '/api/media/uploads/upload_test/complete') return { r: { ok: true }, j: { media } };
    throw new Error('unexpected test route ' + route);
  });
  h.context.captureRecognition = async id => { assert.equal(id, 'media_test'); recognizeCount++; };
  h.run('recognizeMedia=captureRecognition');
  await h.click('recordBtn'); h.recorders[0].emit('retained-original');
  h.click('finishVoiceBtn'); await h.recorders[0].finish();
  assert.equal(await h.run('pendingRecordingBlob').text(), 'retained-original');
  assert.equal(h.run('voiceUploadPending'), true);
  assert.equal(recognizeCount, 0);
  assert.match(h.element('voiceHint').textContent, /尚未保存/);
  assert.equal(h.element('retryVoiceUploadBtn').disabled, false);
  let prevented = false;
  h.windowListeners.beforeunload({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  failPart = false;
  await h.click('retryVoiceUploadBtn');
  assert.equal(partKeys.length, 2); assert.equal(partKeys[0], partKeys[1]);
  assert.deepEqual(partBytes, ['retained-original', 'retained-original']);
  assert.equal(h.run('pendingRecordingBlob'), null);
  assert.equal(h.run('voiceUploadPending'), false);
  assert.equal(h.element('retryVoiceUploadBtn').classList.contains('hidden'), true);
  assert.equal(recognizeCount, 1);
  assert.equal(h.element('recordBtn').disabled, false);
});

test('successful recognition waits through safety and event linking, then renders top-level safety', async () => {
  const h = harness();
  const safety = { danger_detected: true, danger_reminder: '顶层危险提醒：请联系专业人员。' };
  const states = [
    saved(),
    { ...saved(), recognition_status: 'succeeded', link_status: 'pending', link_pending_reason: 'safety_scan_pending' },
    { ...saved(), recognition_status: 'succeeded', link_status: 'pending', link_pending_reason: 'event_link_pending' },
    { ...saved(), recognition_status: 'succeeded', link_status: 'linked', event_link: { record_id: 'rec_test' }, local_safety: safety,
      recognition: { text: '已识别文字', is_mock: false, local_safety: { danger_detected: false } } },
  ];
  let reads = 0, posts = 0;
  h.setApi(async (route, options) => {
    if (route === '/api/media') return { r: { ok: true }, j: { media: [states[Math.min(reads, states.length - 1)]] } };
    if (route === '/api/media/media_test/recognize') { posts++; return { r: { ok: true }, j: { accepted: true } }; }
    if (route === '/api/media/media_test') return { r: { ok: true }, j: { media: states[Math.min(reads++, states.length - 1)] } };
    throw new Error('unexpected test route ' + route);
  });
  await h.run('recognizeMedia("media_test")');
  assert.equal(posts, 1);
  assert.equal(reads, 4);
  assert.equal(h.waits, 2);
  const result = h.element('media-media_test:.media-result');
  assert.match(result.innerHTML, /顶层危险提醒/);
  assert.match(result.innerHTML, /已识别文字/);
  assert.equal(result.children.at(-1).textContent, '核对识别记录');
  assert.match(h.element('mediaStatus').textContent, /识别文字已保留/);
  assert.equal(h.run('recognitionBusy.size'), 0);
});

test('a duplicate recognition click shares the in-flight request', async () => {
  const h = harness(); let resolveRead, posts = 0;
  const pending = new Promise(resolve => { resolveRead = resolve; });
  h.setApi(async (route, options) => {
    if (route === '/api/media') return { r: { ok: true }, j: { media: [] } };
    if (route.endsWith('/recognize')) { posts++; return { r: { ok: true }, j: {} }; }
    return pending;
  });
  const first = h.run('recognizeMedia("media_test")');
  await h.run('recognizeMedia("media_test")');
  resolveRead({ r: { ok: true }, j: { media: { ...saved(), recognition_status: 'succeeded',
    event_link: { record_id: 'rec_test' }, recognition: { text: 'existing result', is_mock: true } } } });
  await first;
  assert.equal(posts, 0);
  assert.equal(h.requests.filter(request => request.route === '/api/media/media_test').length, 1);
});
