"""Stateless owner access for the local-first hosted application.

Health records and decryption keys never enter this module.  It protects only
the hosted AI and backup capabilities with a signed, short-lived cookie plus a
double-submit CSRF value carried inside that signed cookie.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie


COOKIE_NAME = "bingli_session"
_LOGIN_FAILURES: dict[str, list[float]] = {}
_LOGIN_LOCK = threading.Lock()


class AccessConfigurationError(RuntimeError):
    pass


def local_first_enabled() -> bool:
    return os.getenv("APP_MODE", "").strip().lower() == "local_first"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _required_secret() -> bytes:
    value = os.getenv("APP_SESSION_SECRET", "")
    if len(value.encode("utf-8")) < 32:
        raise AccessConfigurationError("app_session_secret_not_configured")
    return value.encode("utf-8")


def configured() -> bool:
    try:
        _required_secret()
    except AccessConfigurationError:
        return False
    password = os.getenv("APP_OWNER_PASSWORD", "")
    password_hash = os.getenv("APP_OWNER_PASSWORD_SHA256", "")
    return len(password) >= 12 or re.fullmatch(r"[0-9a-fA-F]{64}", password_hash) is not None


def verify_password(value: object) -> bool:
    if not isinstance(value, str):
        return False
    expected = os.getenv("APP_OWNER_PASSWORD", "")
    expected_hash = os.getenv("APP_OWNER_PASSWORD_SHA256", "").strip().lower()
    if expected:
        return len(expected) >= 12 and hmac.compare_digest(value.encode("utf-8"), expected.encode("utf-8"))
    if re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
        actual = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return hmac.compare_digest(actual, expected_hash)
    return False


def login_allowed(identifier: str, now: float | None = None) -> bool:
    current = time.time() if now is None else now
    window = 15 * 60
    with _LOGIN_LOCK:
        recent = [value for value in _LOGIN_FAILURES.get(identifier, []) if value > current - window]
        _LOGIN_FAILURES[identifier] = recent
        return len(recent) < 5


def record_login_result(identifier: str, success: bool, now: float | None = None) -> None:
    current = time.time() if now is None else now
    with _LOGIN_LOCK:
        if success:
            _LOGIN_FAILURES.pop(identifier, None)
        else:
            _LOGIN_FAILURES.setdefault(identifier, []).append(current)


def reset_login_limiter() -> None:
    """Clear in-memory limiter state for process-isolated tests."""
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.clear()


@dataclass(frozen=True)
class Session:
    csrf: str
    expires_at: int


def issue_session(now: int | None = None) -> tuple[Session, str]:
    secret = _required_secret()
    current = int(time.time() if now is None else now)
    try:
        ttl = int(os.getenv("APP_SESSION_TTL_SECONDS", "43200"))
    except ValueError as error:
        raise AccessConfigurationError("app_session_ttl_invalid") from error
    if ttl < 300 or ttl > 604800:
        raise AccessConfigurationError("app_session_ttl_invalid")
    payload = {
        "v": 1,
        "iat": current,
        "exp": current + ttl,
        "csrf": secrets.token_urlsafe(24),
        "nonce": secrets.token_urlsafe(12),
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64encode(hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).digest())
    return Session(payload["csrf"], payload["exp"]), f"{encoded}.{signature}"


def parse_session(cookie_header: str | None, now: int | None = None) -> Session | None:
    if not cookie_header:
        return None
    try:
        cookies = SimpleCookie(); cookies.load(cookie_header)
        token = cookies[COOKIE_NAME].value
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _b64encode(hmac.new(_required_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_b64decode(encoded))
        current = int(time.time() if now is None else now)
        if payload.get("v") != 1 or type(payload.get("exp")) is not int or payload["exp"] <= current:
            return None
        csrf = payload.get("csrf")
        if not isinstance(csrf, str) or len(csrf) < 20:
            return None
        return Session(csrf, payload["exp"])
    except (AccessConfigurationError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def request_authorized(cookie_header: str | None, csrf_header: str | None = None, *, write: bool) -> Session | None:
    session = parse_session(cookie_header)
    if session is None:
        return None
    if write and (not csrf_header or not hmac.compare_digest(csrf_header, session.csrf)):
        return None
    return session


def cookie_header(token: str, *, clear: bool = False) -> str:
    secure = os.getenv("APP_COOKIE_SECURE", "true").strip().lower() not in {"0", "false", "off", "no"}
    same_site = os.getenv("APP_COOKIE_SAMESITE", "Strict").strip().capitalize()
    if same_site not in {"Strict", "Lax", "None"}:
        raise AccessConfigurationError("app_cookie_samesite_invalid")
    if same_site == "None" and not secure:
        raise AccessConfigurationError("app_cookie_samesite_none_requires_secure")
    parts = [f"{COOKIE_NAME}={'' if clear else token}", "Path=/", "HttpOnly", f"SameSite={same_site}"]
    if secure:
        parts.append("Secure")
    if clear:
        parts.append("Max-Age=0")
    return "; ".join(parts)
