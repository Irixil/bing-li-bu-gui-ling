import hashlib

import pytest

from backend import app_access


def configure(monkeypatch):
    monkeypatch.setenv("APP_MODE", "local_first")
    monkeypatch.setenv("APP_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("APP_OWNER_PASSWORD", "a sufficiently long password")
    monkeypatch.setenv("APP_COOKIE_SECURE", "false")


def test_owner_session_is_signed_expiring_and_requires_csrf_on_writes(monkeypatch):
    configure(monkeypatch)
    session, token = app_access.issue_session()
    cookie = f"other=x; {app_access.COOKIE_NAME}={token}"

    parsed = app_access.parse_session(cookie)
    assert parsed == session
    assert app_access.request_authorized(cookie, session.csrf, write=True) is not None
    assert app_access.request_authorized(cookie, "wrong", write=True) is None
    assert app_access.parse_session(cookie + "tampered") is None
    assert app_access.parse_session(cookie, now=session.expires_at) is None


def test_password_can_be_supplied_as_sha256_without_exposing_it_in_session(monkeypatch):
    monkeypatch.setenv("APP_SESSION_SECRET", "s" * 32)
    monkeypatch.delenv("APP_OWNER_PASSWORD", raising=False)
    monkeypatch.setenv("APP_OWNER_PASSWORD_SHA256", hashlib.sha256(b"another long password").hexdigest())

    assert app_access.configured() is True
    assert app_access.verify_password("another long password") is True
    assert app_access.verify_password("wrong") is False
    _, token = app_access.issue_session(now=100)
    assert "another" not in token


def test_incomplete_access_configuration_fails_closed(monkeypatch):
    monkeypatch.delenv("APP_SESSION_SECRET", raising=False)
    monkeypatch.delenv("APP_OWNER_PASSWORD", raising=False)
    monkeypatch.delenv("APP_OWNER_PASSWORD_SHA256", raising=False)
    assert app_access.configured() is False
    assert app_access.verify_password("anything") is False


def test_login_failures_are_bounded_and_success_clears_the_window():
    app_access.reset_login_limiter()
    for offset in range(5):
        assert app_access.login_allowed("127.0.0.1", now=100 + offset)
        app_access.record_login_result("127.0.0.1", False, now=100 + offset)
    assert app_access.login_allowed("127.0.0.1", now=110) is False
    assert app_access.login_allowed("127.0.0.1", now=1000) is True
    app_access.record_login_result("127.0.0.1", False, now=1000)
    app_access.record_login_result("127.0.0.1", True, now=1001)
    assert app_access.login_allowed("127.0.0.1", now=1002) is True


def test_cookie_policy_supports_split_services_without_weak_defaults(monkeypatch):
    configure(monkeypatch)
    strict = app_access.cookie_header("token")
    assert "SameSite=Strict" in strict
    assert "Secure" not in strict

    monkeypatch.setenv("APP_COOKIE_SECURE", "true")
    monkeypatch.setenv("APP_COOKIE_SAMESITE", "None")
    cross_site = app_access.cookie_header("token")
    assert "SameSite=None" in cross_site
    assert "Secure" in cross_site

    monkeypatch.setenv("APP_COOKIE_SECURE", "false")
    with pytest.raises(app_access.AccessConfigurationError, match="requires_secure"):
        app_access.cookie_header("token")
