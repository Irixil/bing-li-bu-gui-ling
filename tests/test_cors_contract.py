from contextlib import contextmanager

import pytest

from backend import server
from backend.store import SQLiteStore
from tests.http_support import HttpClient, running_http_server

ALLOWED_FRONTEND_ORIGIN = "http://localhost:5173"


@contextmanager
def running_api(tmp_path, monkeypatch, allowed_origin):
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    monkeypatch.setattr(
        server, "STORE", SQLiteStore(tmp_path / "cors-contract.sqlite3")
    )
    monkeypatch.setattr(server, "ALLOWED_ORIGIN", allowed_origin)
    with running_http_server(server.Handler) as base_url:
        yield HttpClient(base_url)


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
    response = client.request("GET", "/health")
    assert response.status == 200
    return response.body["session_token"]


def event_payload(text):
    return {"raw_text": text, "source_kind": "elder", "actor_name": "老人"}


def test_allowed_origin_preflight_advertises_cors_write_contract(cross_origin_api):
    response = cross_origin_api.request(
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

    assert response.status == 204
    assert response.body is None
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_FRONTEND_ORIGIN
    assert "origin" in comma_separated_header_values(response.headers, "Vary")
    assert "post" in comma_separated_header_values(
        response.headers, "Access-Control-Allow-Methods"
    )
    assert {
        "content-type",
        "idempotency-key",
        "x-session-token",
    } <= comma_separated_header_values(response.headers, "Access-Control-Allow-Headers")


def test_write_from_unexpected_origin_is_rejected_even_with_valid_session_token(
    cross_origin_api,
):
    response = cross_origin_api.request(
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

    assert response.status == 403
    assert response.body == {"ok": False, "error": "csrf_or_origin_rejected"}
    assert response.headers.get("Access-Control-Allow-Origin") is None


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

    response = same_origin_api.request(
        "POST",
        "/api/events",
        event_payload(f"{origin_mode} 写入可用。"),
        headers=headers,
    )

    assert response.status == 201
    assert response.body["ok"] is True
    assert response.body["created"] is True
    assert response.body["event"]["raw_text"] == f"{origin_mode} 写入可用。"
