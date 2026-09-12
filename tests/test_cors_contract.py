import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

import pytest

from backend import server
from backend.store import SQLiteStore


ALLOWED_FRONTEND_ORIGIN = "http://localhost:5173"


class HttpClient:
    def __init__(self, base_url):
        self.base_url = base_url
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, body=None, headers=None):
        request = urllib.request.Request(
            self.base_url + path,
            method=method,
            headers=headers or {},
            data=None if body is None else json.dumps(body).encode("utf-8"),
        )
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw_body = response.read()
            payload = json.loads(raw_body) if raw_body else None
            return response.status, response.headers, payload


@contextmanager
def running_api(tmp_path, monkeypatch, allowed_origin):
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    monkeypatch.setattr(
        server, "STORE", SQLiteStore(tmp_path / "cors-contract.sqlite3")
    )
    monkeypatch.setattr(server, "ALLOWED_ORIGIN", allowed_origin)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield HttpClient(f"http://127.0.0.1:{httpd.server_port}")
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=2)


@pytest.fixture
def cross_origin_api(tmp_path, monkeypatch):
    with running_api(tmp_path, monkeypatch, ALLOWED_FRONTEND_ORIGIN) as client:
        yield client


@pytest.fixture
def same_origin_api(tmp_path, monkeypatch):
    with running_api(tmp_path, monkeypatch, "") as client:
        yield client


def comma_separated_header_values(headers, name):
    return {
        value.strip().lower()
        for value in headers.get(name, "").split(",")
        if value.strip()
    }


def session_token(client):
    status, _, body = client.request("GET", "/health")
    assert status == 200
    return body["session_token"]


def event_payload(text):
    return {"raw_text": text, "source_kind": "elder", "actor_name": "老人"}


def test_allowed_origin_preflight_advertises_cors_write_contract(cross_origin_api):
    status, headers, body = cross_origin_api.request(
        "OPTIONS",
        "/api/events",
        headers={
            "Origin": ALLOWED_FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "Content-Type, Idempotency-Key, X-Session-Token"
            ),
        },
    )

    assert status == 204
    assert body is None
    assert headers["Access-Control-Allow-Origin"] == ALLOWED_FRONTEND_ORIGIN
    assert "origin" in comma_separated_header_values(headers, "Vary")
    assert "post" in comma_separated_header_values(
        headers, "Access-Control-Allow-Methods"
    )
    assert {
        "content-type",
        "idempotency-key",
        "x-session-token",
    } <= comma_separated_header_values(headers, "Access-Control-Allow-Headers")


def test_write_from_unexpected_origin_is_rejected_even_with_valid_session_token(
    cross_origin_api,
):
    status, headers, body = cross_origin_api.request(
        "POST",
        "/api/events",
        event_payload("今天散步二十分钟。"),
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": "unexpected-origin",
            "X-Session-Token": session_token(cross_origin_api),
            "Origin": "https://unexpected.example",
        },
    )

    assert status == 403
    assert body == {"ok": False, "error": "csrf_or_origin_rejected"}
    assert headers.get("Access-Control-Allow-Origin") is None


@pytest.mark.parametrize("origin_mode", ["same-origin", "no-origin"])
def test_session_token_write_is_usable_for_same_origin_or_originless_caller(
    same_origin_api, origin_mode
):
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": f"write-{origin_mode}",
        "X-Session-Token": session_token(same_origin_api),
    }
    if origin_mode == "same-origin":
        headers["Origin"] = same_origin_api.base_url

    status, _, body = same_origin_api.request(
        "POST",
        "/api/events",
        event_payload(f"{origin_mode} 写入可用。"),
        headers=headers,
    )

    assert status == 201
    assert body["ok"] is True
    assert body["created"] is True
    assert body["event"]["raw_text"] == f"{origin_mode} 写入可用。"
