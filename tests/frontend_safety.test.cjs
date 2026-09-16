const test = require('node:test');
const assert = require('node:assert/strict');
const { scanDanger } = require('../frontend/safety.js');

test('device scanner keeps emergency notices conservative', () => {
  for (const text of ['胸痛', '呼吸很困难', '突然右手无力', '血压：180/110', '呕吐停不下来']) {
    assert.equal(scanDanger(text).danger_detected, true, text);
  }
  assert.deepEqual(scanDanger('没有胸痛').matched_rules, []);
  assert.deepEqual(scanDanger('没有胸痛但喘不上气').matched_rules, ['breathing']);
  assert.equal(scanDanger('不确定有没有胸痛').danger_detected, true);
  assert.equal(scanDanger('今天散步二十分钟').danger_detected, false);
  assert.equal('safe' in scanDanger('今天散步二十分钟'), false);
});

test('low heart rate stays a professional-review candidate, not a diagnosis', () => {
  const result = scanDanger('历史资料：心率40次/分，当前未核实。');
  assert.equal(result.danger_detected, false);
  assert.deepEqual(result.clinical_review_flags, ['low_heart_rate_candidate']);
  assert.equal(result.clinical_review_required, true);
  assert.match(result.clinical_review_notice, /不是诊断/);
  assert.equal(scanDanger('心率41次/分').clinical_review_required, false);
});
