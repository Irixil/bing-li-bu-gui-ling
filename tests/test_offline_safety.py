import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from backend import adapter
from backend.safety import DANGER_REMINDER, scan_danger
from backend.store import SQLiteStore


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'records.sqlite3'))
    monkeypatch.setenv('MODEL_PROVIDER', 'mock')
    from backend import server
    store = SQLiteStore(str(tmp_path / 'records.sqlite3'))
    monkeypatch.setattr(server, 'STORE', store)
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{httpd.server_port}'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(method, path, body=None, key=None):
        headers = {'Content-Type': 'application/json', 'X-Session-Token': server.SESSION_TOKEN}
        if key:
            headers['Idempotency-Key'] = key
        req = urllib.request.Request(base + path, method=method, headers=headers,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            response = opener.open(req, timeout=5)
        except urllib.error.HTTPError as ex:
            response = ex
        with response:
            return response.status, json.load(response)

    yield request, store
    httpd.shutdown()
    httpd.server_close()
    worker.join(timeout=2)


def create(request, text, key='input'):
    status, body = request('POST', '/api/events',
                          {'raw_text': text, 'source_kind': 'elder', 'actor_name': '演示用户'}, key)
    assert status == 201
    return body['event']


@pytest.mark.parametrize('text', ['今天散步，吃饭和睡觉都和平时一样。', '胸口疼，喘不上气'])
@pytest.mark.parametrize('failure', ['offline', 'timeout', 'invalid_json', 'empty', 'unexpected', 'invalid_object'])
def test_failure_keeps_original_and_notice(api, monkeypatch, text, failure):
    request, store = api
    event = create(request, text)
    rid = event['record_id']
    expected = scan_danger(text)
    # Saving alone must return the notice, before any model call.
    assert event['local_safety'] == expected

    class Broken:
        def complete_json(self, *_):
            saved = SQLiteStore(store.path).get(rid)
            assert saved['raw_text'] == text
            assert saved['local_safety'] == expected
            if failure == 'offline':
                raise urllib.error.URLError('network unavailable')
            if failure == 'timeout':
                raise TimeoutError('provider timeout')
            if failure == 'invalid_json':
                raise json.JSONDecodeError('invalid', 'no-json', 0)
            if failure == 'empty':
                return None
            if failure == 'invalid_object':
                return {'summary': 'missing required fields'}
            raise RuntimeError('provider internal error; must not leak this body')

    monkeypatch.setattr(adapter, 'provider_from', lambda: Broken())
    status, result = request('POST', f'/api/events/{rid}/organize', {'expected_version': 1})
    assert status == 422
    assert result['ok'] is False and result['ai_failed'] is True
    assert result['raw_text_preserved'] is True
    assert 'output' not in result
    assert result['local_safety'] == expected
    assert result['danger_detected'] == expected['danger_detected']
    assert 'provider internal error' not in json.dumps(result)
    status, saved = request('GET', f'/api/events/{rid}')
    assert status == 200
    assert saved['event']['raw_text'] == text
    assert saved['event']['draft'] is None
    assert saved['event']['state'] == 'inbox' and saved['event']['version'] == 1
    history, audit = store.history(rid)
    assert history and audit[-1]['action'] == 'organize_failed'
    assert audit[-1]['details']['failure_type']
    assert audit[-1]['details']['local_safety'] == expected
    restored = SQLiteStore(store.path)
    assert restored.get(rid)['local_safety'] == expected
    status, card = request('POST', '/api/handoffs', {})
    assert status == 201
    assert card['handoff']['items'][0]['local_safety'] == expected
    assert ('local_danger_detected' in card['handoff']['items'][0]['unresolved_reasons']) == expected['danger_detected']
    assert request('POST', f'/api/events/{rid}/review', {'expected_version': 1, 'action': 'confirm'})[0] == 409


def test_success_keeps_existing_flow_and_cannot_clear_local_warning(api, monkeypatch):
    request, store = api
    raw = '胸口疼，喘不上气'
    event = create(request, raw)

    class MissedDanger:
        def complete_json(self, prompt, payload):
            out = adapter.MockProvider().complete_json(prompt, payload)
            out.update(escalation_level='none', review_role='family')
            return out

    monkeypatch.setattr(adapter, 'provider_from', lambda: MissedDanger())
    status, result = request('POST', f"/api/events/{event['record_id']}/organize", {'expected_version': 1})
    assert status == 200 and result['ai_failed'] is False
    assert result['danger_detected'] and result['safety_guard_applied']
    assert result['output']['escalation_level'] == 'emergency'
    assert result['output']['review_role'] == 'emergency_services'
    assert result['output']['plan_change_allowed'] is False
    assert DANGER_REMINDER in result['output']['follow_up_questions']
    status, result = request('POST', f"/api/events/{event['record_id']}/review",
                             {'expected_version': 2, 'action': 'confirm', 'note': '仅确认原话'})
    assert status == 200 and result['event']['confirmation_scope'] == 'record_accuracy'
    assert store.handoff()['items'][0]['unresolved']


@pytest.mark.parametrize('text', ['胸痛', '胸口疼', '胸闷', '喘不上气', '呼吸不上来', '呼吸困难',
    '叫不醒', '昏迷', '意识不清', '抽搐', '大量出血', '止不住血', '突然不能说话', '口角歪',
    '一侧无力', '严重摔倒', '头部受伤', '血压200/90', '血压160/120', '血压70/40',
    '喘不过气', '喊不醒', '嘴角歪', '血流不止', '血压１８０／１１０', '收缩压190',
    '呼吸很困难', '说话含糊', '突发右侧无力', '严重出血', '摔倒', '呕吐停不下来'])
def test_requested_and_legacy_rules(text):
    assert scan_danger(text)['danger_detected']


@pytest.mark.parametrize('text', ['今天睡得很好', '散步二十分钟', '血压120/80', '今天吃了早饭', '准备下周去复诊'])
def test_ordinary_inputs_do_not_match(text):
    result = scan_danger(text)
    assert not result['danger_detected'] and result['danger_reminder'] is None


def test_revision_keeps_owner_and_rescans_raw_text(tmp_path):
    store = SQLiteStore(str(tmp_path / 'r.sqlite3'))
    household = store.create_household('演示', '演示用户', password='valid-password')
    event, _ = store.create({'raw_text': '胸痛', 'actor_name': '演示用户', 'source_kind': 'elder'}, 'k', household_id=household['household_id'])
    new = store.revise(event['record_id'], 1, {'raw_text': '修正录入：今天散步正常', 'actor_name': '演示用户', 'source_kind': 'elder', 'reason': '输入错误'}, '演示用户')
    assert new['household_id'] == household['household_id']
    assert not new['local_safety']['danger_detected']
    assert store.get(event['record_id'])['local_safety']['danger_detected']
    assert [x['record_id'] for x in store.handoff(household['household_id'])['items']] == [new['record_id']]


@pytest.mark.parametrize('violation', ['schema', 'source_id', 'quote', 'occurred_time', 'recorded_time', 'medical_advice'])
def test_existing_validators_still_reject_and_preserve_raw(api, monkeypatch, violation):
    request, store = api
    event = create(request, '今天散步二十分钟。')

    class Invalid:
        def complete_json(self, prompt, payload):
            out = adapter.MockProvider().complete_json(prompt, payload)
            if violation == 'schema':
                out['event_kind'] = 'unsupported'
            elif violation == 'source_id':
                out['claims'][0]['record_id'] = 'invented-id'
            elif violation == 'quote':
                out['claims'][0]['quote'] = '原文没有这句话'
            elif violation == 'occurred_time':
                out['time']['occurred'] = '2026-01-01T10:00:00Z'
            elif violation == 'recorded_time':
                out['time']['recorded'] = '2026-01-01T10:00:00Z'
            else:
                out['summary'] = '建议停药'
            return out

    monkeypatch.setattr(adapter, 'provider_from', lambda: Invalid())
    status, result = request('POST', f"/api/events/{event['record_id']}/organize", {'expected_version': 1})
    assert status == 422 and result['ai_failed']
    assert store.get(event['record_id'])['draft'] is None
    assert request('GET', f"/api/events/{event['record_id']}")[1]['event']['raw_text'] == event['raw_text']
