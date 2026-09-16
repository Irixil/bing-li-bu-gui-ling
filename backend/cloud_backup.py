"""Short-lived grants for encrypted browser backups in a private TOS bucket.

Only ciphertext archives are sent to TOS.  Object names are generated here,
credentials stay server-side, and every returned URL expires quickly.
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


MAX_BACKUP_BYTES = 100 * 1024 * 1024
CONTENT_TYPE = "application/vnd.bingli.encrypted+json"
_REGION = re.compile(r"^[a-z]{2}-[a-z0-9-]{2,40}$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PREFIX = re.compile(r"^[a-z0-9][a-z0-9/_-]{0,80}/$")


class CloudBackupError(RuntimeError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class BackupConfig:
    access_key: str | None
    secret_key: str | None
    security_token: str | None
    endpoint: str
    public_endpoint: str
    region: str
    bucket: str
    prefix: str
    grant_seconds: int


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise CloudBackupError("backup_not_configured", 503)
    return value


@dataclass(frozen=True)
class RequestCredentials:
    access_key: str
    secret_key: str
    security_token: str


def load_config(credentials: RequestCredentials | None = None, *, require_credentials: bool = True) -> BackupConfig:
    region = _required("TOS_REGION")
    bucket = _required("TOS_BUCKET")
    endpoint = _required("TOS_ENDPOINT").removeprefix("https://").removeprefix("http://").rstrip("/")
    prefix = os.getenv("TOS_BACKUP_PREFIX", "backups/").strip()
    try:
        grant_seconds = int(os.getenv("TOS_GRANT_SECONDS", "300"))
    except ValueError as error:
        raise CloudBackupError("backup_configuration_invalid", 503) from error
    expected_public_endpoint = f"tos-{region}.volces.com"
    expected_internal_endpoint = f"tos-{region}.ivolces.com"
    public_endpoint = os.getenv("TOS_PUBLIC_ENDPOINT", "https://" + expected_public_endpoint).strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    use_role = os.getenv("TOS_USE_VEFAAS_ROLE", "true").strip().lower() not in {"0", "false", "off", "no"}
    access_key = credentials.access_key if credentials else os.getenv("TOS_ACCESS_KEY", "").strip() or None
    secret_key = credentials.secret_key if credentials else os.getenv("TOS_SECRET_KEY", "").strip() or None
    security_token = credentials.security_token if credentials else os.getenv("TOS_SECURITY_TOKEN", "").strip() or None
    if (
        not _REGION.fullmatch(region)
        or not _BUCKET.fullmatch(bucket)
        or endpoint not in {expected_public_endpoint, expected_internal_endpoint}
        or public_endpoint != expected_public_endpoint
        or not _PREFIX.fullmatch(prefix)
        or not 60 <= grant_seconds <= 900
    ):
        raise CloudBackupError("backup_configuration_invalid", 503)
    if require_credentials and (not access_key or not secret_key or use_role and not security_token):
        raise CloudBackupError("backup_credentials_unavailable", 503)
    if not use_role and (not access_key or not secret_key):
        raise CloudBackupError("backup_not_configured", 503)
    return BackupConfig(
        access_key=access_key,
        secret_key=secret_key,
        security_token=security_token,
        endpoint="https://" + endpoint,
        public_endpoint="https://" + public_endpoint,
        region=region,
        bucket=bucket,
        prefix=prefix,
        grant_seconds=grant_seconds,
    )


def configured() -> bool:
    try:
        load_config(require_credentials=False)
        import tos  # noqa: F401
    except (CloudBackupError, ImportError):
        return False
    return True


def _client(config: BackupConfig):
    try:
        import tos
    except ImportError as error:
        raise CloudBackupError("backup_sdk_unavailable", 503) from error
    return tos.TosClientV2(
        config.access_key,
        config.secret_key,
        config.endpoint,
        config.region,
        security_token=config.security_token,
        max_retry_count=0,
        request_timeout=15,
        socket_timeout=15,
    )


def _safe_object_key(config: BackupConfig, key: object) -> str:
    if not isinstance(key, str) or len(key) > 180 or not key.startswith(config.prefix) or not key.endswith(".bingli"):
        raise CloudBackupError("backup_key_invalid")
    relative = key[len(config.prefix) :]
    if not relative or ".." in relative or not re.fullmatch(r"[0-9A-Za-z/_-]+\.bingli", relative):
        raise CloudBackupError("backup_key_invalid")
    return key


def _safe_sdk_call(call: Callable[[], object]):
    try:
        return call()
    except CloudBackupError:
        raise
    except Exception as error:
        # Never expose SDK messages because they can contain signed URLs.
        raise CloudBackupError("backup_service_unavailable", 502) from error


def create_upload_grant(size: object, sha256: object, *, credentials: RequestCredentials | None = None, now: datetime | None = None) -> dict:
    if type(size) is not int or not 1 <= size <= MAX_BACKUP_BYTES:
        raise CloudBackupError("backup_size_invalid", 413)
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise CloudBackupError("backup_sha256_invalid")
    config = load_config(credentials)
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y/%m/%d/%Y%m%dT%H%M%SZ")
    key = f"{config.prefix}{timestamp}-{secrets.token_hex(12)}.bingli"
    headers = {
        "content-type": CONTENT_TYPE,
        "x-tos-meta-sha256": sha256,
        "x-tos-meta-size": str(size),
    }
    client = _client(config)
    try:
        import tos

        output = _safe_sdk_call(
            lambda: client.pre_signed_url(
                tos.HttpMethodType.Http_Method_Put,
                config.bucket,
                key,
                expires=config.grant_seconds,
                header=headers,
                alternative_endpoint=config.public_endpoint,
                is_signed_all_headers=True,
            )
        )
        return {
            "object_key": key,
            "method": "PUT",
            "url": output.signed_url,
            # Browsers set Host themselves and forbid JavaScript from doing so.
            "headers": {key: value for key, value in output.signed_header.items() if key.lower() != "host"},
            "expires_in": config.grant_seconds,
            "size": size,
            "sha256": sha256,
        }
    finally:
        client.close()


def create_download_grant(key: object, *, credentials: RequestCredentials | None = None) -> dict:
    config = load_config(credentials)
    safe_key = _safe_object_key(config, key)
    client = _client(config)
    try:
        import tos

        output = _safe_sdk_call(
            lambda: client.pre_signed_url(
                tos.HttpMethodType.Http_Method_Get,
                config.bucket,
                safe_key,
                expires=config.grant_seconds,
                alternative_endpoint=config.public_endpoint,
            )
        )
        return {
            "object_key": safe_key,
            "method": "GET",
            "url": output.signed_url,
            "headers": {key: value for key, value in output.signed_header.items() if key.lower() != "host"},
            "expires_in": config.grant_seconds,
        }
    finally:
        client.close()


def list_backups(limit: int = 20, *, credentials: RequestCredentials | None = None) -> list[dict]:
    config = load_config(credentials)
    client = _client(config)
    try:
        output = _safe_sdk_call(
            lambda: client.list_objects_type2(
                config.bucket,
                prefix=config.prefix,
                max_keys=max(1, min(limit, 50)),
                list_only_once=True,
            )
        )
        values = [
            {
                "object_key": item.key,
                "size": item.size,
                "last_modified": item.last_modified.astimezone(timezone.utc).isoformat() if item.last_modified else None,
                "etag": item.etag,
            }
            for item in output.contents
            if isinstance(item.key, str) and item.key.startswith(config.prefix) and item.key.endswith(".bingli")
        ]
        values.sort(key=lambda item: item["last_modified"] or "", reverse=True)
        return values[:limit]
    finally:
        client.close()
