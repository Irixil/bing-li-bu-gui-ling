"""Create and restore consistent local backups.

``backup`` remains the database-only interface used by the original text MVP.
``backup_media_bundle`` adds immutable media originals and a hash manifest;
``restore_media_bundle`` verifies the whole bundle before publishing either the
database or media directory.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_VERSION = 1


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError('数据库不存在；请先保存至少一条记录')
    if destination.exists():
        raise ValueError('备份目标已存在；请选择新文件名，避免覆盖')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('备份完整性检查失败')
    return destination


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _safe_relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("媒体引用不安全")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("媒体引用不安全")
    return Path(*relative.parts)


def _open_verified_original(media_root, relative_path, expected_sha256):
    if not isinstance(expected_sha256, str) or _SHA256.fullmatch(expected_sha256) is None:
        raise ValueError("媒体原件校验信息无效")
    root = Path(media_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("媒体目录不存在或不安全")
    relative = _safe_relative_path(relative_path)
    candidate = root.joinpath(relative)
    try:
        if candidate.is_symlink():
            raise OSError
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(candidate, flags)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError
        return descriptor, relative, info.st_size
    except OSError:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        raise ValueError("媒体原件缺失") from None


def _copy_verified_original(media_root, relative_path, expected_sha256, destination):
    descriptor, relative, expected_size = _open_verified_original(
        media_root, relative_path, expected_sha256
    )
    target = Path(destination).joinpath(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(descriptor, "rb") as source, target.open("xb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        raise ValueError("媒体原件复制失败") from None
    if size != expected_size or digest.hexdigest() != expected_sha256:
        try:
            target.unlink()
        except OSError:
            pass
        raise ValueError("媒体原件校验失败")
    return relative, size


def _referenced_media(database):
    with sqlite3.connect(Path(database)) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='media'"
        ).fetchone()
        if table is None:
            return []
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(media)").fetchall()
        }
        required = {"media_id", "relative_path", "sha256"}
        if not required <= columns:
            raise ValueError("媒体数据库结构不完整")
        where = " WHERE save_status='saved'" if "save_status" in columns else ""
        rows = connection.execute(
            "SELECT media_id,relative_path,sha256 FROM media"
            + where
            + " ORDER BY media_id"
        ).fetchall()
    result = []
    for media_id, relative_path, sha256 in rows:
        if not isinstance(media_id, str) or not media_id:
            raise ValueError("媒体数据库结构不完整")
        result.append(
            {
                "media_id": media_id,
                "relative_path": relative_path,
                "sha256": sha256,
            }
        )
    return result


def backup_media_bundle(source_database, source_media_root, destination):
    """Back up one SQLite snapshot and every original referenced by it."""

    source_database = Path(source_database).resolve()
    source_media_root = Path(source_media_root)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("备份目标已存在；请选择新目录，避免覆盖")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    try:
        database_copy = backup(source_database, staging / "records.sqlite3")
        manifest_media = []
        media_destination = staging / "media"
        media_destination.mkdir()
        for item in _referenced_media(database_copy):
            try:
                relative, size = _copy_verified_original(
                    source_media_root,
                    item["relative_path"],
                    item["sha256"],
                    media_destination,
                )
            except ValueError as exc:
                if str(exc) == "媒体原件校验失败":
                    raise
                if str(exc) == "媒体原件缺失":
                    raise
                raise
            manifest_media.append(
                {
                    "media_id": item["media_id"],
                    "relative_path": relative.as_posix(),
                    "sha256": item["sha256"],
                    "size_bytes": size,
                }
            )
        manifest = {
            "version": _MANIFEST_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": "records.sqlite3",
            "database_sha256": _sha256(database_copy),
            "media": manifest_media,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.rename(staging, destination)
        return destination
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _read_manifest(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("备份包不存在或不安全")
    try:
        manifest_path = bundle / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise OSError
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("备份清单无效") from None
    if (
        not isinstance(value, dict)
        or value.get("version") != _MANIFEST_VERSION
        or not isinstance(value.get("media"), list)
        or value.get("database") != "records.sqlite3"
        or not isinstance(value.get("database_sha256"), str)
        or _SHA256.fullmatch(value["database_sha256"]) is None
    ):
        raise ValueError("备份清单无效")
    return value


def _verify_bundle(bundle, manifest):
    database = Path(bundle) / manifest["database"]
    if database.is_symlink() or not database.is_file():
        raise ValueError("备份数据库缺失")
    if _sha256(database) != manifest["database_sha256"]:
        raise ValueError("备份数据库损坏")
    try:
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("备份数据库损坏")
    except sqlite3.Error:
        raise ValueError("备份数据库损坏") from None
    seen = set()
    for item in manifest["media"]:
        if not isinstance(item, dict) or set(item) != {
            "media_id",
            "relative_path",
            "sha256",
            "size_bytes",
        }:
            raise ValueError("备份清单无效")
        relative = _safe_relative_path(item["relative_path"])
        if relative.as_posix() in seen:
            raise ValueError("备份清单无效")
        seen.add(relative.as_posix())
        try:
            descriptor, _, size = _open_verified_original(
                Path(bundle) / "media", item["relative_path"], item["sha256"]
            )
            with os.fdopen(descriptor, "rb") as stream:
                digest = hashlib.sha256()
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
        except ValueError as exc:
            if str(exc) == "媒体原件缺失":
                raise ValueError("媒体原件缺失") from None
            raise
        if (
            type(item["size_bytes"]) is not int
            or item["size_bytes"] < 1
            or size != item["size_bytes"]
            or digest.hexdigest() != item["sha256"]
        ):
            raise ValueError("媒体原件损坏")


def restore_media_bundle(bundle, destination_database, destination_media_root):
    """Verify a bundle, then restore it without overwriting local data."""

    bundle = Path(bundle).resolve()
    destination_database = Path(destination_database).resolve()
    destination_media_root = Path(destination_media_root).resolve()
    if destination_database.exists() or destination_media_root.exists():
        raise ValueError("恢复目标已存在；不会覆盖已有数据")
    manifest = _read_manifest(bundle)
    _verify_bundle(bundle, manifest)
    destination_database.parent.mkdir(parents=True, exist_ok=True)
    destination_media_root.parent.mkdir(parents=True, exist_ok=True)
    temporary_database = Path(
        tempfile.mkstemp(
            prefix=f".{destination_database.name}.tmp-",
            dir=destination_database.parent,
        )[1]
    )
    temporary_media = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_media_root.name}.tmp-",
            dir=destination_media_root.parent,
        )
    )
    media_published = False
    try:
        shutil.copyfile(bundle / manifest["database"], temporary_database)
        for item in manifest["media"]:
            _copy_verified_original(
                bundle / "media",
                item["relative_path"],
                item["sha256"],
                temporary_media,
            )
        os.rename(temporary_media, destination_media_root)
        media_published = True
        os.rename(temporary_database, destination_database)
        return {
            "database": destination_database,
            "media_root": destination_media_root,
        }
    except BaseException:
        try:
            temporary_database.unlink()
        except OSError:
            pass
        shutil.rmtree(temporary_media, ignore_errors=True)
        if media_published:
            shutil.rmtree(destination_media_root, ignore_errors=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='runtime/records.sqlite3')
    parser.add_argument('--out', default='runtime/backups/records-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
    args = parser.parse_args()
    print(backup(args.db, args.out))
