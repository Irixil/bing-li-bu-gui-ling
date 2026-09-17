const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const frontend = path.join(__dirname, '../frontend');
const read = name => fs.readFileSync(path.join(frontend, name), 'utf8');
const markup = read('index.html');
const app = read('app.js');
const styles = read('styles.css');
const ios = read('ios.css');
const splash = read('splash.js');
const localStore = read('local-store.js');

test('complete elder frontend remains the only user-facing shell', () => {
  const nav = markup.match(/<nav class="bottom-nav"[\s\S]*?<\/nav>/)?.[0] || '';
  assert.equal((nav.match(/class="nav-item/g) || []).length, 3);
  for (const view of ['homeView', 'voiceView', 'photoCaptureView', 'recordsView', 'archiveView', 'settingsView']) {
    assert.match(markup, new RegExp(`id="${view}"`));
  }
  for (const control of ['recordBtn', 'voiceTextInput', 'voiceTextSend', 'photoInput', 'eventsList', 'archivePhotos', 'handoffBtn']) {
    assert.match(markup, new RegExp(`id="${control}"`));
  }
  assert.match(markup, /class="conversation-stream"/);
  assert.match(markup, /runtime-config\.js/);
  assert.match(markup, /local-store\.js/);
  assert.match(app, /globalThis\.HealthLocal\.request/);
});

test('the original mascot and voice-first identity are retained', () => {
  assert.ok(fs.existsSync(path.join(frontend, 'assets/brand-mascot.png')));
  assert.ok((markup.match(/assets\/brand-mascot\.png/g) || []).length >= 3);
  assert.match(markup, /身体感觉怎么样/);
  assert.match(markup, /慢慢说，我帮你记着/);
  assert.match(markup, /说给我听/);
});

test('text can be recorded without replacing the voice-first navigation', () => {
  assert.doesNotMatch(markup, /id="textView"|data-view="textView"|id="rawText"/);
  assert.match(markup, /可以单独用文字记录/);
  assert.match(app, /related_record_ids:related/);
  assert.match(app, /if\(saveBusy\)return/);
});

test('prototype demo identity and simulated diagnostic chat are not shipped', () => {
  const shipped = `${markup}\n${app}`;
  assert.doesNotMatch(shipped, /王大爷|72 岁|上海|诊断交接|语音问答|边说边补全/);
  assert.match(app, /不是实时问诊/);
  assert.match(markup, /核对记录，不等于诊断/);
  assert.match(markup, /不是诊断，也不会建议增减药物/);
});

test('mobile shell includes elderly touch, safe-area, dynamic viewport and reduced-motion safeguards', () => {
  assert.match(styles, /min-height:\s*48px/);
  assert.match(styles, /min-height:\s*100dvh/);
  assert.match(styles, /prefers-reduced-motion:\s*reduce/);
  assert.match(ios, /safe-area-inset-bottom/);
  assert.doesNotMatch(ios, /height:\s*844px/);
});

test('splash is dismissible, session-scoped and reduced-motion aware', () => {
  assert.match(markup, /id="splashSkip"/);
  assert.match(splash, /sessionStorage/);
  assert.match(splash, /Escape/);
  assert.match(splash, /prefers-reduced-motion/);
  assert.match(splash, /setTimeout\(closeSplash/);
});

test('elder flow uses family device binding without a second password prompt', () => {
  const shipped = `${markup}\n${localStore}`;
  assert.doesNotMatch(shipped, /cloudPassword|cloudLoginForm|网站访问密码|\/api\/app\/login/);
  assert.match(localStore, /\/api\/app\/device\/activate/);
  assert.match(localStore, /family_device_binding_required/);
  assert.match(localStore, /history\.replaceState/);
  assert.match(markup, /老人不需要输入网站密码/);
  assert.match(markup, /本机记录始终可以继续使用/);
});
