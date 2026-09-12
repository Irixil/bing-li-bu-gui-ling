"""Protocol/security checks run offline; no credentials or external APIs used."""
import json
import io
import traceback
import urllib.error
from email.message import Message
from urllib.response import addinfourl

import pytest

from backend.adapter import (
    AdapterError, Config, DeepSeekProvider, ModelScopeProvider,
    OpenAICompatibleProvider, provider_from,
)
from backend import model_client
from backend.model_client import (
    ChatCompletionsClient, MAX_ERROR_RESPONSE_BYTES, MAX_RESPONSE_BYTES, ModelClientError,
    PROTECTED_BODY_FIELDS, completion_url,
)


SECRET = 'test-token-must-never-appear-in-errors'


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    import os
    for key in list(os.environ):
        if key.startswith(('MODEL_', 'MODELSCOPE_', 'DEEPSEEK_', 'LLM_')):
            monkeypatch.delenv(key)


def client(**overrides):
    options = dict(base_url='https://unit-test.invalid/v1', model='test-model', api_key=SECRET)
    options.update(overrides)
    return ChatCompletionsClient(**options)


def envelope(content='{"ok": true}', reason='stop'):
    return {'choices': [{'message': {'role': 'assistant', 'content': content}, 'finish_reason': reason}]}


class Response:
    status = 200
    headers = {'Content-Type': 'application/json; charset=utf-8'}

    def __init__(self, data):
        self.raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.read_limits = []

    def __enter__(self): return self
    def __exit__(self, *_): pass

    def read(self, limit):
        self.read_limits.append(limit)
        return self.raw[:limit]


def serve_response(monkeypatch, data):
    response = Response(data)
    monkeypatch.setattr(model_client, '_open_request', lambda *args: response)
    return response


@pytest.mark.parametrize(('given', 'expected'), [
    ('https://api.example/v1', 'https://api.example/v1/chat/completions'),
    ('https://api.example/v1/', 'https://api.example/v1/chat/completions'),
    ('https://api.example/v1/chat/completions', 'https://api.example/v1/chat/completions'),
    ('https://api.example/v1/chat/completions/', 'https://api.example/v1/chat/completions'),
    ('https://api.example/custom/prefix/v1', 'https://api.example/custom/prefix/v1/chat/completions'),
    ('https://api.example', 'https://api.example/chat/completions'),
    ('http://localhost:9000/v1', 'http://localhost:9000/v1/chat/completions'),
    ('http://127.0.0.1:9000/v1', 'http://127.0.0.1:9000/v1/chat/completions'),
    ('http://[::1]:9000/v1', 'http://[::1]:9000/v1/chat/completions'),
])
def test_url_normalization(given, expected):
    assert completion_url(given) == expected


@pytest.mark.parametrize('url', [
    '', '/v1', 'ftp://api.example/v1', 'http://api.example/v1',
    'http://192.168.1.1/v1', 'http://localhost.attacker.test/v1',
    'https:///v1', 'https://user:secret@api.example/v1',
    'https://@api.example/v1', 'https://api.example/v1?key=secret',
    'https://api.example/v1?', 'https://api.example/v1#secret',
    'https://api.example/v1#', 'https://api.example:bad/v1',
    'https://api.example:0/v1', 'https://api.example:99999/v1',
    'https://api.example/\nv1', ' https://api.example/v1',
    'https://api.example\\@attacker.test/v1', 'https://%65xample.test/v1',
])
def test_invalid_urls_fail_before_network(monkeypatch, url):
    monkeypatch.setattr(model_client, '_open_request', lambda *args: pytest.fail('must not send'))
    with pytest.raises(ModelClientError) as error:
        client(base_url=url)
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize(('provider_name', 'expected'), [
    ('openai_compatible', OpenAICompatibleProvider), ('openai', OpenAICompatibleProvider),
    ('custom', OpenAICompatibleProvider), ('modelscope', ModelScopeProvider),
    ('魔搭', ModelScopeProvider), ('deepseek', DeepSeekProvider),
    ('deepseek-ai', DeepSeekProvider),
])
def test_provider_factory_retains_aliases(provider_name, expected):
    assert type(provider_from(Config(provider=provider_name, base_url='https://example.invalid/v1', model='test', token=SECRET))) is expected


@pytest.mark.parametrize('provider_name', ['openai_compatible', 'openai', 'custom'])
def test_generic_provider_without_explicit_url_never_sends(monkeypatch, provider_name):
    monkeypatch.setattr(model_client, '_open_request', lambda *args: pytest.fail('must not send'))
    config = Config(provider=provider_name, model='relay/model', token=SECRET)
    assert config.base_url == ''
    with pytest.raises(AdapterError) as error:
        provider_from(config)
    assert error.value.code == 'model_configuration_invalid'
    with pytest.raises(AdapterError):
        OpenAICompatibleProvider(config)


@pytest.mark.parametrize(('provider_class', 'expected_url'), [
    (ModelScopeProvider, 'https://api-inference.modelscope.cn/v1/chat/completions'),
    (DeepSeekProvider, 'https://api.deepseek.com/v1/chat/completions'),
])
def test_direct_legacy_provider_uses_only_its_own_default(provider_class, expected_url):
    provider = provider_class(Config(model='legacy/model', token=SECRET))
    assert provider.client.url == expected_url


def test_generic_environment_configuration(monkeypatch):
    values = {
        'MODEL_PROVIDER': 'openai_compatible', 'LLM_BASE_URL': 'https://relay.example/v1/chat/completions',
        'LLM_MODEL': 'vendor/test-model', 'LLM_API_KEY': SECRET, 'LLM_JSON_MODE': 'false',
        'LLM_EXTRA_BODY_JSON': '{"enable_thinking":false}', 'MODEL_MAX_TOKENS': '8192',
        'MODEL_TIMEOUT_SECONDS': '60',
    }
    for key, value in values.items(): monkeypatch.setenv(key, value)
    config = Config.from_env()
    assert config.base_url == values['LLM_BASE_URL']
    assert config.model == values['LLM_MODEL'] and config.token == SECRET
    assert config.json_mode is False and config.extra_body == {'enable_thinking': False}
    assert config.max_tokens == 8192 and config.timeout == 60
    assert SECRET not in repr(config)
    assert isinstance(provider_from(config), OpenAICompatibleProvider)


@pytest.mark.parametrize(('provider_name', 'token_key', 'model_key', 'default_url'), [
    ('modelscope', 'MODELSCOPE_ACCESS_TOKEN', 'MODELSCOPE_MODEL', 'https://api-inference.modelscope.cn/v1'),
    ('modelscope', 'MODELSCOPE_TOKEN', 'MODELSCOPE_MODEL', 'https://api-inference.modelscope.cn/v1'),
    ('deepseek', 'DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', 'https://api.deepseek.com/v1'),
])
def test_legacy_environment_stays_compatible(monkeypatch, provider_name, token_key, model_key, default_url):
    for key, value in {'MODEL_PROVIDER': provider_name, token_key: SECRET, model_key: 'legacy-model'}.items():
        monkeypatch.setenv(key, value)
    config = Config.from_env()
    assert (config.token, config.model, config.base_url) == (SECRET, 'legacy-model', default_url)
    assert config.max_tokens == 4096 and config.json_mode is None


@pytest.mark.parametrize(('key', 'value'), [
    ('LLM_JSON_MODE', 'sometimes'), ('MODEL_MAX_TOKENS', '0'), ('MODEL_MAX_TOKENS', '1.5'),
    ('MODEL_MAX_TOKENS', '-1'), ('MODEL_TIMEOUT_SECONDS', 'nan'), ('MODEL_TIMEOUT_SECONDS', 'inf'),
    ('MODEL_TIMEOUT_SECONDS', '0'), ('LLM_EXTRA_BODY_JSON', '[]'),
    ('LLM_EXTRA_BODY_JSON', '{bad json'), ('LLM_EXTRA_BODY_JSON', '{"x":1,"x":2}'),
    ('LLM_EXTRA_BODY_JSON', '{"x":NaN}'), ('LLM_EXTRA_BODY_JSON', '{"x":1e400}'),
])
def test_invalid_configuration_fails_closed(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(AdapterError): Config.from_env()


@pytest.mark.parametrize('field', sorted(PROTECTED_BODY_FIELDS))
def test_extra_body_cannot_override_core_request(field):
    with pytest.raises(ModelClientError, match='核心字段'):
        client(extra_body={field: 'override'})


@pytest.mark.parametrize(('provider_class', 'json_mode', 'expected_json'), [
    (OpenAICompatibleProvider, None, False), (ModelScopeProvider, None, False),
    (DeepSeekProvider, None, True), (DeepSeekProvider, False, False),
    (ModelScopeProvider, True, True), (OpenAICompatibleProvider, True, True),
])
def test_exact_single_nonstream_request(monkeypatch, provider_class, json_mode, expected_json):
    requests = []

    def capture(request, timeout):
        requests.append((request, timeout))
        return Response(envelope())

    monkeypatch.setattr(model_client, '_open_request', capture)
    config = Config(base_url='https://relay.example/v1/chat/completions', model='test-model',
                    token=SECRET, timeout=60, json_mode=json_mode, max_tokens=8192,
                    extra_body={'enable_thinking': False})
    assert provider_class(config).complete_json('system prompt', {'raw_text': '测试原文'}) == {'ok': True}
    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.full_url == config.base_url and request.get_method() == 'POST' and timeout == 60
    assert request.headers['Authorization'] == 'Bearer ' + SECRET
    body = json.loads(request.data)
    assert body['messages'] == [
        {'role': 'system', 'content': 'system prompt'},
        {'role': 'user', 'content': '{"raw_text": "测试原文"}'},
    ]
    assert body['stream'] is False and body['temperature'] == 0
    assert body['enable_thinking'] is False and body['max_tokens'] == 8192
    assert body['model'] == config.model
    if expected_json: assert body['response_format'] == {'type': 'json_object'}
    else: assert 'response_format' not in body


@pytest.mark.parametrize('content', [
    '', '  ', None, [{'text': '{"ok":true}'}], '[]', 'null', '"text"',
    '{"ok":true} trailing', 'prefix {"ok":true}', '{"ok":true,"ok":false}',
    '{"nested":{"duplicate":1,"duplicate":2}}', '{"value":NaN}', '{"value":1e400}',
    '```json\n{"ok":true}\n``` trailing',
])
def test_invalid_model_content_rejected(monkeypatch, content):
    serve_response(monkeypatch, envelope(content))
    with pytest.raises(ModelClientError): client().complete_json('system', {})


@pytest.mark.parametrize('data', [
    b'{"choices":[],"choices":[]}', b'{"choices":[{"message":{"content":"{}","content":"{}"},"finish_reason":"stop"}]}',
    b'not json', b'\xff', [], {}, {'choices': []},
    {'choices': [envelope()['choices'][0], envelope()['choices'][0]]},
    envelope('{}', None), envelope('{}', 'tool_calls'), envelope('{}', 'content_filter'),
    envelope('{}', 'length'),
])
def test_invalid_or_incomplete_envelope_rejected(monkeypatch, data):
    serve_response(monkeypatch, data)
    with pytest.raises(ModelClientError): client().complete_json('system', {})


@pytest.mark.parametrize('role', ['user', 'system', 'tool', '', None])
def test_explicit_nonassistant_role_is_rejected(monkeypatch, role):
    data = envelope()
    data['choices'][0]['message']['role'] = role
    serve_response(monkeypatch, data)
    with pytest.raises(ModelClientError, match='role'):
        client().complete_json('system', {})


def test_missing_role_remains_compatible(monkeypatch):
    data = envelope()
    del data['choices'][0]['message']['role']
    serve_response(monkeypatch, data)
    assert client().complete_json('system', {}) == {'ok': True}


@pytest.mark.parametrize('error_body', [{'message': SECRET}, SECRET, True, ['failure']])
def test_success_envelope_with_nonempty_error_is_rejected(monkeypatch, error_body):
    data = envelope()
    data['error'] = error_body
    serve_response(monkeypatch, data)
    with pytest.raises(ModelClientError) as error:
        client().complete_json('system', {})
    assert SECRET not in str(error.value)


def test_read_is_bounded(monkeypatch):
    response = serve_response(monkeypatch, b' ' * (MAX_RESPONSE_BYTES + 10))
    with pytest.raises(ModelClientError) as error:
        client().complete_json('system', {})
    assert error.value.code == 'model_response_too_large'
    assert response.read_limits == [MAX_RESPONSE_BYTES + 1]


def test_event_stream_content_type_rejected(monkeypatch):
    response = serve_response(monkeypatch, envelope())
    response.headers = {'Content-Type': 'text/event-stream'}
    with pytest.raises(ModelClientError, match='Content-Type'):
        client().complete_json('system', {})
    assert response.read_limits == []


@pytest.mark.parametrize(('failure', 'expected_code', 'status'), [
    (TimeoutError(SECRET), 'model_timeout', None),
    (urllib.error.URLError(TimeoutError(SECRET)), 'model_timeout', None),
    (urllib.error.URLError(SECRET), 'model_network_error', None),
    (urllib.error.HTTPError('https://secret.example/' + SECRET, 401, SECRET, {}, None), 'model_http_error', 401),
    (urllib.error.HTTPError('https://secret.example/' + SECRET, 429, SECRET, {}, None), 'model_http_error', 429),
    (urllib.error.HTTPError('https://secret.example/' + SECRET, 302, SECRET, {}, None), 'model_redirect_rejected', 302),
])
def test_failures_are_sanitized_without_retry(monkeypatch, failure, expected_code, status):
    calls = []

    def failed(request, timeout):
        calls.append(request.full_url)
        raise failure

    monkeypatch.setattr(model_client, '_open_request', failed)
    provider = OpenAICompatibleProvider(Config(base_url='https://example.invalid/v1', model='test', token=SECRET))
    with pytest.raises(AdapterError) as captured:
        provider.complete_json('system', {})
    error = captured.value
    assert error.code == expected_code and error.status == status
    assert SECRET not in ''.join(traceback.format_exception(error))
    assert 'secret.example' not in str(error) and len(calls) == 1


MODELSCOPE_URL = 'https://api-inference.modelscope.cn/v1'
BINDING_MESSAGE = 'Please bind your Alibaba Cloud account before use.'


def serve_http_error(monkeypatch, body, *, status=401):
    class ErrorBody(io.BytesIO):
        def __init__(self, raw):
            super().__init__(raw)
            self.read_limits = []

        def read(self, limit=-1):
            self.read_limits.append(limit)
            return super().read(limit)

    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    stream = ErrorBody(raw)

    def failed(request, timeout):
        raise urllib.error.HTTPError(request.full_url, status, SECRET, {}, stream)

    monkeypatch.setattr(model_client, '_open_request', failed)
    return stream


@pytest.mark.parametrize('status', [401, 403])
def test_modelscope_binding_error_is_fixed_and_sanitized(monkeypatch, status):
    stream = serve_http_error(monkeypatch, {
        'error': {'message': BINDING_MESSAGE, 'debug': SECRET}, 'request': SECRET,
    }, status=status)
    with pytest.raises(ModelClientError) as captured:
        client(base_url=MODELSCOPE_URL).complete_json('system', {})
    error = captured.value
    assert error.code == 'model_account_binding_required' and error.status == status
    assert str(error) == '魔搭账号需先绑定阿里云账号'
    assert SECRET not in ''.join(traceback.format_exception(error))
    assert BINDING_MESSAGE not in str(error)
    assert stream.read_limits == [MAX_ERROR_RESPONSE_BYTES + 1]
    assert stream.closed


@pytest.mark.parametrize('base_url', [
    'https://unit-test.invalid/v1',
    'https://api-inference.modelscope.cn.attacker.invalid/v1',
    'https://modelscope.cn/v1',
])
def test_other_hosts_never_classify_modelscope_error(monkeypatch, base_url):
    stream = serve_http_error(monkeypatch, {'error': {'message': BINDING_MESSAGE}})
    with pytest.raises(ModelClientError) as captured:
        client(base_url=base_url).complete_json('system', {})
    assert captured.value.code == 'model_http_error' and captured.value.status == 401
    assert str(captured.value) == '模型请求失败：HTTP 401'
    assert stream.read_limits == [] and stream.closed


@pytest.mark.parametrize('body', [
    {'error': {'message': BINDING_MESSAGE + ' ' + SECRET}},
    {'error': {'message': BINDING_MESSAGE.lower()}},
    {'message': BINDING_MESSAGE},
    {'error': BINDING_MESSAGE},
    {'error': {'message': [BINDING_MESSAGE]}},
    b'{bad-json ' + SECRET.encode(),
    b'\xff',
    b'{"error":{"message":"' + BINDING_MESSAGE.encode() + b'","message":"other"}}',
    json.dumps({'error': {'message': BINDING_MESSAGE}, 'debug': SECRET}).encode()
    + b' ' * MAX_ERROR_RESPONSE_BYTES,
])
def test_unrecognized_modelscope_error_retains_http_failure(monkeypatch, body):
    stream = serve_http_error(monkeypatch, body)
    with pytest.raises(ModelClientError) as captured:
        client(base_url=MODELSCOPE_URL).complete_json('system', {})
    error = captured.value
    assert error.code == 'model_http_error' and error.status == 401
    assert str(error) == '模型请求失败：HTTP 401'
    assert SECRET not in ''.join(traceback.format_exception(error))
    assert stream.read_limits == [MAX_ERROR_RESPONSE_BYTES + 1] and stream.closed


@pytest.mark.parametrize('status', [302, 429, 500])
def test_modelscope_non_auth_errors_are_not_read(monkeypatch, status):
    stream = serve_http_error(monkeypatch, {'error': {'message': BINDING_MESSAGE}}, status=status)
    with pytest.raises(ModelClientError) as captured:
        client(base_url=MODELSCOPE_URL).complete_json('system', {})
    expected = 'model_redirect_rejected' if status == 302 else 'model_http_error'
    assert captured.value.code == expected and captured.value.status == status
    assert stream.read_limits == [] and stream.closed


def test_modelscope_error_body_read_failure_retains_http_failure(monkeypatch):
    class BrokenBody(io.BytesIO):
        def read(self, limit=-1):
            raise OSError(SECRET)

    stream = BrokenBody()

    def failed(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, SECRET, {}, stream)

    monkeypatch.setattr(model_client, '_open_request', failed)
    with pytest.raises(ModelClientError) as captured:
        client(base_url=MODELSCOPE_URL).complete_json('system', {})
    error = captured.value
    assert error.code == 'model_http_error' and error.status == 401
    assert str(error) == '模型请求失败：HTTP 401'
    assert SECRET not in ''.join(traceback.format_exception(error))
    assert stream.closed


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
def test_urllib_redirect_handler_never_follows(monkeypatch, status):
    received = []

    def fake_http_open(self, request):
        received.append(request.full_url)
        headers = Message()
        headers['Location'] = 'http://localhost:9999/target'
        response = addinfourl(io.BytesIO(b''), headers, request.full_url, status)
        response.msg = 'Redirect'
        return response

    # Exercise the real urllib opener, HTTPErrorProcessor and redirect handler,
    # replacing only the network send so the test also works without bind access.
    monkeypatch.setattr(model_client.urllib.request.HTTPHandler, 'http_open', fake_http_open)
    with pytest.raises(ModelClientError) as captured:
        client(base_url='http://localhost:9999/v1').complete_json('system', {})
    assert captured.value.code == 'model_redirect_rejected'
    assert received == ['http://localhost:9999/v1/chat/completions']
