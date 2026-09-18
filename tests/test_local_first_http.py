from backend import server
from backend.store import SQLiteStore
from tests.http_support import HttpClient, running_http_server
from tests.test_media_api import PNG, multipart


def configure(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_MODE", "local_first")
    monkeypatch.setenv("APP_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("APP_OWNER_PASSWORD", "a sufficiently long password")
    monkeypatch.setenv("APP_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOWED_ORIGIN", "http://127.0.0.1:5173")
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    monkeypatch.setattr(server, "STORE", SQLiteStore(tmp_path / "must-stay-empty.sqlite3"))


def login(client):
    response = client.request("POST", "/api/app/login", {"password": "a sufficiently long password"})
    assert response.status == 200
    return response.headers["Set-Cookie"].split(";", 1)[0], response.body["csrf_token"]


def test_local_first_health_and_session_do_not_issue_legacy_storage_token(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    with running_http_server(server.Handler) as base_url:
        client = HttpClient(base_url, {"Content-Type": "application/json"})
        health = client.request("GET", "/health")
        assert health.status == 200
        assert health.body["mode"] == "local_first"
        assert health.body["storage"] == "encrypted_on_device"
        assert "session_token" not in health.body

        session = client.request("GET", "/api/app/session")
        assert session.body == {"ok": True, "authenticated": False}
        legacy = client.request("GET", "/api/events")
        assert legacy.status == 404
        assert legacy.body["error"] == "legacy_api_disabled"


def test_local_first_backend_is_api_only_and_allows_only_the_frontend_origin(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    with running_http_server(server.Handler) as base_url:
        client = HttpClient(base_url, {"Content-Type": "application/json"})
        root = client.request("GET", "/")
        assert root.status == 200
        assert root.body == {"ok": True, "service": "bingli-beta-api", "kind": "api", "frontend_hosted": False}

        allowed = client.request(
            "OPTIONS",
            "/api/app/login",
            headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST"},
        )
        assert allowed.status == 204
        assert allowed.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
        assert allowed.headers["Access-Control-Allow-Credentials"] == "true"

        rejected = client.request(
            "OPTIONS",
            "/api/app/login",
            headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"},
        )
        assert rejected.status == 403
        assert rejected.body["error"] == "origin_rejected"
        assert rejected.headers.get("Access-Control-Allow-Origin") is None


def test_split_frontend_can_login_and_reuse_cookie_cross_port(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    origin = "http://127.0.0.1:5173"
    with running_http_server(server.Handler) as base_url:
        client = HttpClient(base_url, {"Content-Type": "application/json", "Origin": origin})
        response = client.request("POST", "/api/app/login", {"password": "a sufficiently long password"})
        assert response.status == 200
        assert response.headers["Access-Control-Allow-Origin"] == origin
        assert response.headers["Access-Control-Allow-Credentials"] == "true"
        cookie = response.headers["Set-Cookie"].split(";", 1)[0]

        session = client.request("GET", "/api/app/session", headers={"Cookie": cookie})
        assert session.status == 200
        assert session.body["authenticated"] is True
        assert session.headers["Access-Control-Allow-Origin"] == origin

        untrusted = client.request(
            "POST",
            "/api/app/login",
            {"password": "a sufficiently long password"},
            headers={"Origin": "https://untrusted.example"},
        )
        assert untrusted.status == 403
        assert untrusted.body["error"] == "csrf_or_origin_rejected"


def test_family_link_activates_a_persistent_device_session(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("APP_DEVICE_SESSION_TTL_SECONDS", "2592000")
    origin = "http://127.0.0.1:5173"
    activation_token, _ = server.app_access.issue_device_activation()
    with running_http_server(server.Handler) as base_url:
        client = HttpClient(base_url, {"Content-Type": "application/json", "Origin": origin})
        activated = client.request("POST", "/api/app/device/activate", {"activation_token": activation_token})
        assert activated.status == 200
        assert activated.body["binding"] == "family_link"
        assert "Max-Age=2592000" in activated.headers["Set-Cookie"]
        assert "HttpOnly" in activated.headers["Set-Cookie"]
        cookie = activated.headers["Set-Cookie"].split(";", 1)[0]

        session = client.request("GET", "/api/app/session", headers={"Cookie": cookie})
        assert session.body["authenticated"] is True
        assert session.body["csrf_token"] == activated.body["csrf_token"]

        rejected = client.request(
            "POST",
            "/api/app/device/activate",
            {"activation_token": activation_token},
            headers={"Origin": "https://untrusted.example"},
        )
        assert rejected.status == 403
        assert rejected.body["error"] == "csrf_or_origin_rejected"


def test_loopback_development_can_bind_silently_but_production_default_cannot(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    origin = "http://127.0.0.1:5173"
    with running_http_server(server.Handler) as base_url:
        client = HttpClient(base_url, {"Content-Type": "application/json", "Origin": origin})
        ordinary = client.request("GET", "/api/app/session")
        assert ordinary.body == {"ok": True, "authenticated": False}

        monkeypatch.setenv("APP_AUTO_BIND_LOOPBACK", "true")
        bound = client.request("GET", "/api/app/session")
        assert bound.body["authenticated"] is True
        assert bound.body["binding"] == "loopback_development"
        assert "Max-Age=" in bound.headers["Set-Cookie"]

        no_origin = HttpClient(base_url, {"Content-Type": "application/json"}).request("GET", "/api/app/session")
        assert no_origin.body == {"ok": True, "authenticated": False}


def test_allowed_frontend_uses_stateless_ai_without_session_or_consent(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    origin = "http://127.0.0.1:5173"
    with running_http_server(server.Handler) as base_url:
        no_origin = HttpClient(base_url, {"Content-Type": "application/json"})
        denied = no_origin.request("POST", "/api/ai/organize", {})
        assert denied.status == 403

        untrusted = HttpClient(base_url, {"Content-Type": "application/json", "Origin": "https://untrusted.example"})
        rejected = untrusted.request(
            "POST",
            "/api/ai/organize",
            {"record_id": "rec_12345678", "raw_text": "今天头晕"},
        )
        assert rejected.status == 403

        client = HttpClient(base_url, {"Content-Type": "application/json", "Origin": origin})
        organized = client.request(
            "POST",
            "/api/ai/organize",
            {
                "record_id": "rec_12345678",
                "raw_text": "今天头晕",
                "source_kind": "elder",
                "recorded_at": "2026-09-16T10:00:00+00:00",
                "history": [],
            },
        )
        assert organized.status == 200
        assert organized.body["raw_text_preserved_on_device"] is True
        assert organized.body["output"]["review_required"] is True
        assert server.STORE.list() == []

def test_local_first_fails_closed_when_access_secret_is_missing(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    monkeypatch.delenv("APP_SESSION_SECRET")
    with running_http_server(server.Handler) as base_url:
        client = HttpClient(base_url, {"Content-Type": "application/json"})
        config = client.request("GET", "/api/app/config")
        assert config.body["access_configured"] is False
        login_attempt = client.request("POST", "/api/app/login", {"password": "a sufficiently long password"})
        assert login_attempt.status == 503
        assert login_attempt.body["error"] == "access_not_configured"
        direct_ai = client.request(
            "POST",
            "/api/ai/organize",
            {"record_id": "rec_12345678", "raw_text": "今天头晕", "history": []},
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert direct_ai.status == 200


def test_media_recognition_uses_a_temporary_original_and_returns_only_the_draft(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    observed = {}

    def recognize(path, **kwargs):
        observed["path"] = path
        observed["bytes"] = path.read_bytes()
        return {"text": "照片上的文字", "provider": "mock", "model": "mock", "is_mock": True, "attempt_id": kwargs["attempt_id"]}

    monkeypatch.setattr(server, "recognize_file", recognize)
    with running_http_server(server.Handler) as base_url:
        client = HttpClient(base_url, {"Content-Type": "application/json", "Origin": "http://127.0.0.1:5173"})
        body, content_type = multipart(
            {"kind": "image", "content_type": "image/png", "attempt_id": "attempt_test"},
            [("file", "report.png", "image/png", PNG)],
        )
        response = client.request(
            "POST",
            "/api/ai/media/recognize",
            raw_body=body,
            headers={"Content-Type": content_type},
        )
        assert response.status == 200
        assert response.body["recognition"]["text"] == "照片上的文字"
        assert observed["bytes"] == PNG
        assert not observed["path"].exists()
        assert server.STORE.list() == []


def test_cloud_backup_grants_require_session_and_csrf(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    expected = {
        "object_key": "backups/2026/09/16/test.bingli",
        "method": "PUT",
        "url": "https://signed.invalid/upload",
        "headers": {"content-type": "application/vnd.bingli.encrypted+json"},
        "expires_in": 300,
        "size": 123,
        "sha256": "a" * 64,
    }
    monkeypatch.setattr(server.cloud_backup, "create_upload_grant", lambda size, sha256, credentials=None: expected)
    monkeypatch.setattr(server.cloud_backup, "list_backups", lambda credentials=None: [{"object_key": expected["object_key"]}])
    with running_http_server(server.Handler) as base_url:
        client = HttpClient(base_url, {"Content-Type": "application/json"})
        denied = client.request("POST", "/api/backups/upload-grant", {"size": 123, "sha256": "a" * 64})
        assert denied.status == 403

        cookie, csrf = login(client)
        missing_csrf = client.request(
            "POST",
            "/api/backups/upload-grant",
            {"size": 123, "sha256": "a" * 64},
            headers={"Cookie": cookie},
        )
        assert missing_csrf.status == 403

        granted = client.request(
            "POST",
            "/api/backups/upload-grant",
            {"size": 123, "sha256": "a" * 64},
            headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        )
        assert granted.status == 201
        assert granted.body["grant"] == expected

        backups = client.request("GET", "/api/backups", headers={"Cookie": cookie})
        assert backups.status == 200
        assert backups.body["backups"][0]["object_key"] == expected["object_key"]
