from scripts import start_app
from scripts.start_app import prepare_app_environment


def test_start_app_selects_local_first_and_generates_only_ephemeral_session_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_SESSION_SECRET", raising=False)
    monkeypatch.delenv("APP_MODE", raising=False)
    env, generated = prepare_app_environment(tmp_path, environ={})
    assert env["APP_MODE"] == "local_first"
    assert generated is True
    assert len(env["APP_SESSION_SECRET"]) >= 32
    assert env["APP_AI_MEDIA_MAX_BYTES"] == str(20 * 1024 * 1024)


def test_check_config_fails_when_device_session_access_is_not_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(start_app, "prepare_app_environment", lambda _root: ({"API_PORT": "18768"}, False))
    monkeypatch.setattr(start_app, "check_demo_configuration", lambda _env: {"模型": []})
    monkeypatch.setattr(start_app.app_access, "session_configured", lambda: False)
    monkeypatch.delenv("APP_OWNER_PASSWORD", raising=False)
    monkeypatch.delenv("APP_OWNER_PASSWORD_SHA256", raising=False)

    assert start_app.main(["--check-config"], root=tmp_path) == 2


def test_check_config_passes_only_when_models_and_device_session_access_are_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(start_app, "prepare_app_environment", lambda _root: ({"API_PORT": "18768"}, False))
    monkeypatch.setattr(start_app, "check_demo_configuration", lambda _env: {"模型": []})
    monkeypatch.setattr(start_app.app_access, "session_configured", lambda: True)

    assert start_app.main(["--check-config"], root=tmp_path) == 0
