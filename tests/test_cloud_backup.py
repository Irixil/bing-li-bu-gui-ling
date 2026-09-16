from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend import cloud_backup


def configure(monkeypatch):
    monkeypatch.setenv("TOS_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("TOS_SECRET_KEY", "test-sk")
    monkeypatch.setenv("TOS_USE_VEFAAS_ROLE", "false")
    monkeypatch.setenv("TOS_REGION", "cn-beijing")
    monkeypatch.setenv("TOS_ENDPOINT", "https://tos-cn-beijing.ivolces.com")
    monkeypatch.setenv("TOS_PUBLIC_ENDPOINT", "https://tos-cn-beijing.volces.com")
    monkeypatch.setenv("TOS_BUCKET", "bingli-beta-backup-test")
    monkeypatch.setenv("TOS_BACKUP_PREFIX", "backups/")
    monkeypatch.setenv("TOS_GRANT_SECONDS", "300")


class FakeClient:
    def __init__(self):
        self.calls = []
        self.closed = False

    def pre_signed_url(self, method, bucket, key, **kwargs):
        self.calls.append((method.value, bucket, key, kwargs))
        return SimpleNamespace(
            signed_url=f"https://signed.invalid/{key}?signature=redacted",
            signed_header=kwargs.get("header", {}),
        )

    def list_objects_type2(self, bucket, **kwargs):
        self.calls.append(("LIST", bucket, kwargs))
        return SimpleNamespace(
            contents=[
                SimpleNamespace(
                    key="backups/2026/09/16/new.bingli",
                    size=123,
                    last_modified=datetime(2026, 9, 16, tzinfo=timezone.utc),
                    etag="etag",
                ),
                SimpleNamespace(
                    key="other/not-visible.bingli",
                    size=1,
                    last_modified=None,
                    etag="ignored",
                ),
            ]
        )

    def close(self):
        self.closed = True


def test_upload_grant_uses_server_generated_key_and_signed_integrity_headers(monkeypatch):
    configure(monkeypatch)
    fake = FakeClient()
    monkeypatch.setattr(cloud_backup, "_client", lambda _config: fake)
    digest = "a" * 64

    grant = cloud_backup.create_upload_grant(
        321,
        digest,
        now=datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc),
    )

    assert grant["method"] == "PUT"
    assert grant["object_key"].startswith("backups/2026/09/16/20260916T080000Z-")
    assert grant["object_key"].endswith(".bingli")
    assert grant["headers"]["content-type"] == cloud_backup.CONTENT_TYPE
    assert grant["headers"]["x-tos-meta-sha256"] == digest
    assert grant["headers"]["x-tos-meta-size"] == "321"
    assert fake.calls[0][3]["is_signed_all_headers"] is True
    assert fake.calls[0][3]["alternative_endpoint"] == "https://tos-cn-beijing.volces.com"
    assert fake.closed is True


def test_download_grant_cannot_escape_backup_prefix(monkeypatch):
    configure(monkeypatch)
    fake = FakeClient()
    monkeypatch.setattr(cloud_backup, "_client", lambda _config: fake)

    with pytest.raises(cloud_backup.CloudBackupError) as error:
        cloud_backup.create_download_grant("../private.bingli")

    assert error.value.code == "backup_key_invalid"
    assert fake.calls == []


def test_list_returns_only_encrypted_backup_objects(monkeypatch):
    configure(monkeypatch)
    fake = FakeClient()
    monkeypatch.setattr(cloud_backup, "_client", lambda _config: fake)

    values = cloud_backup.list_backups()

    assert values == [
        {
            "object_key": "backups/2026/09/16/new.bingli",
            "size": 123,
            "last_modified": "2026-09-16T00:00:00+00:00",
            "etag": "etag",
        }
    ]
    assert fake.closed is True


def test_configuration_rejects_arbitrary_endpoints(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("TOS_ENDPOINT", "https://attacker.invalid")

    with pytest.raises(cloud_backup.CloudBackupError) as error:
        cloud_backup.load_config()

    assert error.value.code == "backup_configuration_invalid"


def test_vefaas_role_mode_is_configured_without_long_lived_keys(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("TOS_USE_VEFAAS_ROLE", "true")
    monkeypatch.delenv("TOS_ACCESS_KEY")
    monkeypatch.delenv("TOS_SECRET_KEY")

    assert cloud_backup.configured() is True
    with pytest.raises(cloud_backup.CloudBackupError) as error:
        cloud_backup.list_backups()
    assert error.value.code == "backup_credentials_unavailable"
