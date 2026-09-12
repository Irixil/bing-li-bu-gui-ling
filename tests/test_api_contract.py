import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from backend import adapter
from backend import server
from backend.store import SQLiteStore


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('MODEL_PROVIDER', 'mock')
    monkeypatch.setattr(server, 'STORE', SQLiteStore(tmp_path / 'records.sqlite3'))
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    base_url = f'http://127.0.0.1:{httpd.server_port}'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(
        method,
        path,
        body=None,
        *,
        idempotency_key=None,
        headers=None,
        raw_body=None,
    ):
        request_headers = {
            'Content-Type': 'application/json',
            'X-Session-Token': server.SESSION_TOKEN,
            **(headers or {}),
        }
        if idempotency_key is not None:
            request_headers['Idempotency-Key'] = idempotency_key
        req = urllib.request.Request(
            base_url + path,
            method=method,
            headers=request_headers,
            data=(
                raw_body
                if raw_body is not None
                else None
                if body is None
                else json.dumps(body).encode('utf-8')
            ),
        )
        try:
            response = opener.open(req, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    yield request
    httpd.shutdown()
    httpd.server_close()
    worker.join(timeout=2)


def save_event(request, text='今天散步二十分钟。', key='event-1'):
    status, result = request(
        'POST',
        '/api/events',
        {'raw_text': text, 'source_kind': 'elder', 'actor_name': '老人'},
        idempotency_key=key,
    )
    assert status == 201
    return result['event']


def test_health_issues_the_token_required_by_writes(api):
    status, health = api('GET', '/health')
    assert status == 200
    assert health['ok'] is True
    assert health['mode'] == 'local_single_household'
    assert health['session_token'] == server.SESSION_TOKEN

    status, result = api(
        'POST',
        '/api/events',
        {'raw_text': '今天散步。', 'source_kind': 'elder', 'actor_name': '老人'},
        idempotency_key='wrong-token',
        headers={'X-Session-Token': 'not-the-health-token'},
    )
    assert status == 403
    assert result == {'ok': False, 'error': 'csrf_or_origin_rejected'}


def test_create_is_idempotent_without_merging_different_payloads(api):
    payload = {'raw_text': '今天散步。', 'source_kind': 'elder', 'actor_name': '老人'}
    status, first = api('POST', '/api/events', payload, idempotency_key='retry-key')
    assert status == 201
    assert first['created'] is True

    status, repeated = api('POST', '/api/events', payload, idempotency_key='retry-key')
    assert status == 200
    assert repeated['created'] is False
    assert repeated['event']['record_id'] == first['event']['record_id']

    status, conflict = api(
        'POST',
        '/api/events',
        {**payload, 'raw_text': '同一个键下不同的内容'},
        idempotency_key='retry-key',
    )
    assert status == 409
    assert conflict == {'ok': False, 'error': 'idempotency_key_payload_mismatch'}

    status, listing = api('GET', '/api/events')
    assert status == 200
    assert [event['record_id'] for event in listing['events']] == [first['event']['record_id']]


def test_create_rejects_missing_idempotency_key(api):
    status, result = api(
        'POST',
        '/api/events',
        {'raw_text': '今天散步。', 'source_kind': 'elder', 'actor_name': '老人'},
    )
    assert status == 400
    assert result == {'ok': False, 'error': 'idempotency_key_required'}


def test_write_rejects_invalid_json_with_a_stable_error_code(api):
    status, result = api(
        'POST',
        '/api/events',
        idempotency_key='invalid-json',
        raw_body=b'{not-json',
    )
    assert status == 400
    assert result == {'ok': False, 'error': 'invalid_json_payload'}


@pytest.mark.parametrize(
    ('payload', 'error'),
    [
        (
            {'raw_text': '今天散步。', 'source_kind': 'invented', 'actor_name': '老人'},
            'invalid_source_kind',
        ),
        (
            {'raw_text': 'x' * 10_001, 'source_kind': 'elder', 'actor_name': '老人'},
            'raw_text_too_long',
        ),
        (
            {'raw_text': '今天散步。', 'source_kind': 'elder', 'actor_name': ''},
            'actor_name_required',
        ),
    ],
)
def test_create_rejects_invalid_event_fields(api, payload, error):
    status, result = api('POST', '/api/events', payload, idempotency_key=error)
    assert status == 400
    assert result == {'ok': False, 'error': error}


def test_saved_event_is_available_from_list_and_detail(api):
    event = save_event(api)

    status, listing = api('GET', '/api/events')
    assert status == 200
    assert listing['ok'] is True
    assert listing['events'] == [event]

    status, detail = api('GET', f"/api/events/{event['record_id']}")
    assert status == 200
    assert detail == {'ok': True, 'event': event}

    status, missing = api('GET', '/api/events/rec_missing')
    assert status == 404
    assert missing == {'ok': False, 'error': 'event_not_found'}

    status, history = api('GET', '/api/events/rec_missing/history')
    assert status == 404
    assert history == {'ok': False, 'error': 'event_not_found'}


@pytest.mark.parametrize('operation', ['organize', 'review', 'revise'])
def test_versioned_write_to_missing_event_returns_not_found(api, operation):
    body = {'expected_version': 1}
    if operation == 'review':
        body.update(action='confirm')
    if operation == 'revise':
        body.update(
            raw_text='更正后的记录',
            source_kind='elder',
            actor_name='老人',
            reason='更正输入',
        )

    status, result = api('POST', f'/api/events/rec_missing/{operation}', body)

    assert status == 404
    assert result == {'ok': False, 'error': 'event_not_found'}


def test_organize_requires_version_before_calling_model(api, monkeypatch):
    event = save_event(api)
    called = False

    def unexpected_model_call(_payload):
        nonlocal called
        called = True
        raise AssertionError('invalid request must not call the model')

    monkeypatch.setattr(server, 'organize_event', unexpected_model_call)
    status, result = api('POST', f"/api/events/{event['record_id']}/organize", {})

    assert status == 400
    assert result == {'ok': False, 'error': 'expected_version_must_positive_integer'}
    assert called is False


@pytest.mark.parametrize('invalid_version', [None, True, '1', 0, -1])
@pytest.mark.parametrize('operation', ['organize', 'review', 'revise'])
def test_versioned_writes_require_a_positive_integer(api, operation, invalid_version):
    event = save_event(api, key=f'{operation}-{invalid_version!r}')
    body = {'expected_version': invalid_version}
    if operation == 'review':
        body.update(action='confirm')
    if operation == 'revise':
        body.update(
            raw_text='更正后的记录',
            source_kind='elder',
            actor_name='老人',
            reason='更正输入',
        )

    status, result = api(
        'POST',
        f"/api/events/{event['record_id']}/{operation}",
        body,
    )

    assert status == 400
    assert result == {'ok': False, 'error': 'expected_version_must_positive_integer'}


def test_organize_rejects_an_already_stale_version_before_calling_model(api, monkeypatch):
    event = save_event(api)
    status, organized = api(
        'POST',
        f"/api/events/{event['record_id']}/organize",
        {'expected_version': event['version']},
    )
    assert status == 200
    assert organized['event']['version'] == 2

    called = False

    def unexpected_model_call(_payload):
        nonlocal called
        called = True
        raise AssertionError('known stale request must not call the model')

    monkeypatch.setattr(server, 'organize_event', unexpected_model_call)
    status, result = api(
        'POST',
        f"/api/events/{event['record_id']}/organize",
        {'expected_version': 1},
    )

    assert status == 409
    assert result == {'ok': False, 'error': 'stale_version'}
    assert called is False


def test_review_enforces_state_and_requires_a_reason_when_returned(api):
    event = save_event(api)

    status, result = api(
        'POST',
        f"/api/events/{event['record_id']}/review",
        {'expected_version': 1, 'action': 'confirm'},
    )
    assert status == 409
    assert result == {'ok': False, 'error': 'confirm_state_invalid'}

    status, organized = api(
        'POST',
        f"/api/events/{event['record_id']}/organize",
        {'expected_version': 1},
    )
    assert status == 200

    status, result = api(
        'POST',
        f"/api/events/{event['record_id']}/review",
        {'expected_version': organized['event']['version'], 'action': 'return'},
    )
    assert status == 400
    assert result == {'ok': False, 'error': 'return_note_required'}

    status, returned = api(
        'POST',
        f"/api/events/{event['record_id']}/review",
        {
            'expected_version': organized['event']['version'],
            'action': 'return',
            'note': '摘要遗漏了发生场景',
        },
    )
    assert status == 200
    assert returned['event']['state'] == 'needs_review'
    assert returned['event']['version'] == 3


def test_review_and_revise_reject_stale_versions(api):
    event = save_event(api)
    record_id = event['record_id']
    status, organized = api(
        'POST',
        f'/api/events/{record_id}/organize',
        {'expected_version': 1},
    )
    assert status == 200
    assert organized['event']['version'] == 2

    status, review_conflict = api(
        'POST',
        f'/api/events/{record_id}/review',
        {'expected_version': 1, 'action': 'confirm'},
    )
    assert status == 409
    assert review_conflict == {'ok': False, 'error': 'stale_version'}

    status, revision_conflict = api(
        'POST',
        f'/api/events/{record_id}/revise',
        {
            'expected_version': 1,
            'raw_text': '更正后的记录',
            'source_kind': 'elder',
            'actor_name': '老人',
            'reason': '更正输入',
        },
    )
    assert status == 409
    assert revision_conflict == {'ok': False, 'error': 'stale_version'}


def test_reorganize_failure_keeps_the_previous_draft_and_version(api, monkeypatch):
    event = save_event(api)
    status, organized = api(
        'POST',
        f"/api/events/{event['record_id']}/organize",
        {'expected_version': 1},
    )
    assert status == 200
    previous = organized['event']
    assert previous['state'] == 'draft'
    assert previous['version'] == 2

    class OfflineProvider:
        def complete_json(self, *_args):
            raise urllib.error.URLError('offline')

    monkeypatch.setattr(adapter, 'provider_from', lambda: OfflineProvider())
    status, failed = api(
        'POST',
        f"/api/events/{event['record_id']}/organize",
        {'expected_version': previous['version']},
    )

    assert status == 422
    assert failed['ai_failed'] is True
    assert failed['raw_text_preserved'] is True
    assert failed['event']['state'] == 'draft'
    assert failed['event']['version'] == previous['version']
    assert failed['event']['draft'] == previous['draft']

    status, detail = api('GET', f"/api/events/{event['record_id']}")
    assert status == 200
    assert detail['event']['version'] == previous['version']
    assert detail['event']['draft'] == previous['draft']


def test_concurrent_http_organize_requests_cannot_commit_the_same_version_twice(
    api, monkeypatch
):
    event = save_event(api)
    both_model_calls_started = threading.Barrier(2)

    def synchronized_organize(payload):
        result = adapter.organize_event(payload, adapter.MockProvider())
        both_model_calls_started.wait(timeout=5)
        return result

    monkeypatch.setattr(server, 'organize_event', synchronized_organize)
    responses = []

    def organize():
        responses.append(
            api(
                'POST',
                f"/api/events/{event['record_id']}/organize",
                {'expected_version': event['version']},
            )
        )

    workers = [threading.Thread(target=organize) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=7)

    assert all(not worker.is_alive() for worker in workers)
    assert sorted(status for status, _ in responses) == [200, 409]
    conflict = next(result for status, result in responses if status == 409)
    assert conflict == {'ok': False, 'error': 'stale_version'}

    status, detail = api('GET', f"/api/events/{event['record_id']}")
    assert status == 200
    assert detail['event']['state'] == 'draft'
    assert detail['event']['version'] == 2


def test_missing_handoff_returns_not_found(api):
    status, result = api('GET', '/api/handoffs/handoff_missing')
    assert status == 404
    assert result == {'ok': False, 'error': 'handoff_not_found'}


def test_unexpected_write_failure_does_not_expose_internal_details(api, monkeypatch):
    def fail_with_internal_detail(_household_id=None):
        raise RuntimeError('private database path: /secret/records.sqlite3')

    monkeypatch.setattr(server.STORE, 'handoff', fail_with_internal_detail)
    status, result = api('POST', '/api/handoffs', {})

    assert status == 500
    assert result == {'ok': False, 'error': 'internal_server_error'}
    assert '/secret/' not in json.dumps(result)


def test_unexpected_read_failure_returns_json_without_internal_details(api, monkeypatch):
    def fail_with_internal_detail(_household_id=None):
        raise RuntimeError('private database path: /secret/records.sqlite3')

    monkeypatch.setattr(server.STORE, 'list', fail_with_internal_detail)
    status, result = api('GET', '/api/events')

    assert status == 500
    assert result == {'ok': False, 'error': 'internal_server_error'}
    assert '/secret/' not in json.dumps(result)


def test_record_can_be_organized_reviewed_revised_and_handed_off(api):
    original = save_event(api, text='今天走路时有些头晕。')
    record_id = original['record_id']

    status, organized = api(
        'POST',
        f'/api/events/{record_id}/organize',
        {'expected_version': original['version']},
    )
    assert status == 200
    assert organized['ok'] is True
    assert organized['ai_failed'] is False
    assert organized['raw_text_preserved'] is True
    assert organized['event']['state'] == 'draft'
    assert organized['event']['version'] == 2
    assert organized['event']['draft'] == organized['output']
    assert {
        'ok',
        'ai_failed',
        'event',
        'output',
        'trace_id',
        'provider',
        'prompt_version',
        'schema_version',
        'latency_ms',
        'safety_guard_applied',
        'raw_text_preserved',
        'local_safety',
        'danger_detected',
        'escalation_level',
        'review_role',
        'danger_reminder',
    } <= organized.keys()

    status, reviewed = api(
        'POST',
        f'/api/events/{record_id}/review',
        {'expected_version': 2, 'action': 'confirm', 'note': '仅确认记录准确'},
    )
    assert status == 200
    assert reviewed['event']['state'] == 'recorded'
    assert reviewed['event']['version'] == 3
    assert reviewed['event']['confirmation_scope'] == 'record_accuracy'

    status, history = api('GET', f'/api/events/{record_id}/history')
    assert status == 200
    assert [item['action'] for item in history['history']] == [
        'created',
        'organized',
        'review_confirm',
    ]
    assert history['history'][0]['snapshot']['raw_text'] == original['raw_text']
    assert {'history', 'audit'} <= history.keys()

    status, generated = api('POST', '/api/handoffs', {})
    assert status == 201
    handoff = generated['handoff']
    assert {'handoff_id', 'created_at', 'household_id', 'items', 'unresolved_count'} == handoff.keys()
    snapshot = next(item for item in handoff['items'] if item['record_id'] == record_id)
    assert snapshot['raw_text'] == original['raw_text']

    status, revised = api(
        'POST',
        f'/api/events/{record_id}/revise',
        {
            'expected_version': 3,
            'raw_text': '修订：今天散步时没有头晕。',
            'source_kind': 'elder',
            'actor_name': '老人',
            'reason': '更正刚才的输入',
        },
    )
    assert status == 201
    replacement = revised['event']
    assert replacement['record_id'] != record_id
    assert replacement['supersedes_id'] == record_id
    assert replacement['state'] == 'inbox'
    assert replacement['version'] == 1

    status, old_detail = api('GET', f'/api/events/{record_id}')
    assert status == 200
    assert old_detail['event']['state'] == 'superseded'
    assert old_detail['event']['raw_text'] == original['raw_text']

    status, fetched_handoff = api('GET', f"/api/handoffs/{handoff['handoff_id']}")
    assert status == 200
    assert fetched_handoff['handoff'] == handoff

    status, latest_handoff = api('POST', '/api/handoffs', {})
    assert status == 201
    latest_ids = [item['record_id'] for item in latest_handoff['handoff']['items']]
    assert record_id not in latest_ids
    assert replacement['record_id'] in latest_ids
