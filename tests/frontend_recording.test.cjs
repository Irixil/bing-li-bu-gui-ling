// Controlled state-machine regression, not proof of a real microphone or ASR.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function harness() {
  let now = 0, nextTimer = 1, permissionCalls = 0, resolvePermission, rejectPermission;
  const timers = new Map(), elements = new Map(), recorders = [], tracks = [];
  function element(id) {
    if (!elements.has(id)) {
      const classes = new Set(id === 'silenceNotice' ? ['hidden'] : []);
      elements.set(id, {
        textContent: '', value: '', disabled: false, innerHTML: '', dataset: {},
        classList: {
          toggle(name, on) { if (on ?? !classes.has(name)) classes.add(name); else classes.delete(name); },
          add(name) { classes.add(name); }, remove(name) { classes.delete(name); },
          contains(name) { return classes.has(name); },
        },
        querySelector() { return element(id + ':span'); }, querySelectorAll() { return []; },
        addEventListener() {}, scrollIntoView() {},
      });
    }
    return elements.get(id);
  }
  const permission = new Promise((resolve, reject) => { resolvePermission = resolve; rejectPermission = reject; });
  class Recorder {
    constructor(stream) { this.stream = stream; this.state = 'inactive'; this.mimeType = 'audio/webm'; this.pauses = 0; this.resumes = 0; this.stops = 0; recorders.push(this); }
    start() { this.state = 'recording'; }
    pause() { assert.equal(this.state, 'recording'); this.state = 'paused'; this.pauses++; }
    resume() { assert.equal(this.state, 'paused'); this.state = 'recording'; this.resumes++; }
    stop() { assert.notEqual(this.state, 'inactive'); this.state = 'inactive'; this.stops++; this.onstop?.(); }
    emit(text) { this.ondataavailable?.({ data: new Blob([text], { type: this.mimeType }) }); }
  }
  const context = vm.createContext({
    console, Blob, FormData, URL, MediaRecorder: Recorder,
    location: { hostname: 'localhost', port: '5173' },
    navigator: { mediaDevices: { getUserMedia() { permissionCalls++; return permission; } } },
    document: { getElementById: element, querySelectorAll: () => [] },
    window: { scrollTo() {} },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true, session_token: 'test', provider: 'mock', events: [] }) }),
    Date: class extends Date { static now() { return now; } },
    setInterval(fn, ms) { const id = nextTimer++; timers.set(id, { fn, ms, interval: true }); return id; },
    clearInterval(id) { timers.delete(id); },
    setTimeout(fn, ms) { const id = nextTimer++; timers.set(id, { fn, ms }); return id; },
    clearTimeout(id) { timers.delete(id); },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8'), context);
  return {
    element, recorders, timers, context,
    click(id) { return element(id).onclick(); },
    run(code) { return vm.runInContext(code, context); },
    advance(ms) { now += ms; for (const timer of [...timers.values()]) if (timer.interval) timer.fn(); },
    allow() { const track = { stopped: false, stop() { this.stopped = true; } }; tracks.push(track); resolvePermission({ getTracks: () => [track] }); },
    deny() { rejectPermission(new Error('NotAllowedError')); },
    get permissionCalls() { return permissionCalls; },
    get tracks() { return tracks; },
  };
}

test('permission pending prevents duplicate start and timer; denial never pretends to record', async () => {
  const h = harness();
  const start = h.click('recordBtn');
  assert.equal(h.element('recordBtn').disabled, true);
  assert.equal(h.element('finishVoiceBtn').disabled, true);
  await h.click('recordBtn');
  h.advance(15000);
  assert.equal(h.permissionCalls, 1);
  assert.equal(h.element('voiceTimer').textContent, '00:00');
  h.deny(); await start;
  assert.equal(h.element('recordBtn').disabled, false);
  assert.equal(h.element('finishVoiceBtn').disabled, true);
  assert.match(h.element('voiceHint').textContent, /未能开启/);
  assert.equal(h.run('mediaRecorder'), null);
  assert.equal(h.timers.size, 0);
});

test('pause freezes timer, resume keeps the same recorder and previous bytes, finish can follow pause', async () => {
  const h = harness();
  const start = h.click('recordBtn');
  h.advance(9000); h.allow(); await start;
  assert.equal(h.element('voiceTimer').textContent, '00:00');
  const recorder = h.recorders[0]; recorder.emit('before pause');
  h.advance(4500); await h.click('recordBtn');
  assert.equal(recorder.state, 'paused');
  assert.equal(recorder.stops, 0);
  assert.equal(h.element('voiceTimer').textContent, '00:04');
  assert.equal(h.element('recordBtn:span').textContent, '继续说');
  assert.equal(h.element('finishVoiceBtn').disabled, false);
  h.advance(12000);
  assert.equal(h.element('voiceTimer').textContent, '00:04');
  await h.click('recordBtn'); h.advance(2000); recorder.emit('after pause');
  assert.equal(h.recorders.length, 1);
  assert.equal(recorder.resumes, 1);
  assert.equal(h.element('voiceTimer').textContent, '00:06');
  await h.click('pauseBtn');
  assert.equal(recorder.state, 'paused');
  assert.equal(h.element('finishVoiceBtn').disabled, false);
  assert.equal(await new Blob(h.run('chunks')).text(), 'before pauseafter pause');
  h.run("stopVoice('test finish')");
  assert.equal(recorder.stops, 1);
  assert.equal(h.tracks[0].stopped, true);
  assert.equal(h.element('voiceTimer').textContent, '00:06');
  assert.equal(h.element('finishVoiceBtn').disabled, true);
});

test('recording does not pretend to detect silence or pause automatically', async () => {
  const h = harness(); const start = h.click('recordBtn'); h.allow(); await start;
  h.advance(12000);
  const silence = [...h.timers.values()].find(timer => !timer.interval && timer.ms === 12000);
  assert.equal(silence, undefined);
  assert.equal(h.recorders[0].state, 'recording');
  assert.equal(h.element('voiceTimer').textContent, '00:12');
  h.advance(7000);
  assert.equal(h.element('voiceTimer').textContent, '00:19');
  assert.equal(h.element('finishVoiceBtn').disabled, false);
});
