import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from backend import adapter
from backend.store import SQLiteStore


def test_failed_organize_can_retry_same_event_without_duplication(tmp_path, monkeypatch):
    """TEXT-RETRY-01: a 422 attempt must remain retryable on the same Event."""
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
        headers = {
            'Content-Type': 'application/json',
            'X-Session-Token': server.SESSION_TOKEN,
        }
        if key:
            headers['Idempotency-Key'] = key
        req = urllib.request.Request(
            base + path,
            method=method,
            headers=headers,
            data=None if body is None else json.dumps(body).encode(),
        )
        try:
            response = opener.open(req, timeout=5)
        except urllib.error.HTTPError as ex:
            response = ex
        with response:
            return response.status, json.load(response)

    raw_text = '今天头晕，想整理一下这条记录。'

    try:
        status, created = request(
            'POST',
            '/api/events',
            {
                'raw_text': raw_text,
                'source_kind': 'elder',
                'actor_name': '演示用户',
            },
            key='task-d-text-retry-01',
        )
        assert status == 201
        record_id = created['event']['record_id']
        source_kind = created['event']['source_kind']
        occurred_time = created['event']['occurred_time']
        status, listed = request('GET', '/api/events')
        assert status == 200
        assert len(listed['events']) == 1
        assert listed['events'][0]['record_id'] == record_id

        class TimedOutProvider:
            def complete_json(self, *_):
                raise TimeoutError('simulated provider timeout')

        monkeypatch.setattr(adapter, 'provider_from', lambda: TimedOutProvider())
        status, failed = request(
            'POST',
            f'/api/events/{record_id}/organize',
            {'expected_version': 1, 'actor_name': '演示用户'},
        )
        assert status == 422
        assert failed['record_id'] == record_id
        assert failed['event']['record_id'] == record_id
        assert failed['event']['raw_text'] == raw_text
        assert failed['event']['source_kind'] == source_kind
        assert failed['event']['occurred_time'] == occurred_time
        assert failed['event']['state'] == 'inbox'
        assert failed['event']['version'] == 1
        assert failed['raw_text_preserved'] is True
        assert len(request('GET', '/api/events')[1]['events']) == 1

        monkeypatch.setattr(adapter, 'provider_from', lambda: adapter.MockProvider())
        status, retried = request(
            'POST',
            f'/api/events/{record_id}/organize',
            {'expected_version': 1, 'actor_name': '演示用户'},
        )
        assert status == 200
        assert retried['ai_failed'] is False
        assert retried['event']['record_id'] == record_id
        assert retried['event']['raw_text'] == raw_text
        assert retried['event']['source_kind'] == source_kind
        assert retried['event']['occurred_time'] == occurred_time
        assert retried['event']['state'] == 'draft'
        assert retried['event']['version'] == 2
        assert retried['raw_text_preserved'] is True

        status, listed = request('GET', '/api/events')
        assert status == 200
        assert len(listed['events']) == 1
        assert listed['events'][0]['record_id'] == record_id
        assert listed['events'][0]['raw_text'] == raw_text
        assert listed['events'][0]['source_kind'] == source_kind
        assert listed['events'][0]['occurred_time'] == occurred_time

        status, history = request('GET', f'/api/events/{record_id}/history')
        assert status == 200
        actions = [item['action'] for item in history['audit']]
        assert actions.count('organize_failed') == 1
        assert actions.count('organized') == 1
        assert actions.index('organize_failed') < actions.index('organized')
        failed_audit = next(item for item in history['audit'] if item['action'] == 'organize_failed')
        organized_audit = next(item for item in history['audit'] if item['action'] == 'organized')
        assert failed_audit['details']['failure_reason'] == '模型超时'
        assert organized_audit['details']['provider'] == 'MockProvider'
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=2)
