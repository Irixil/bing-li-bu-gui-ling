import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.backup import backup, backup_media_bundle, restore_media_bundle
from backend.media_backend import LocalMediaBackend
from backend.media_store import MediaStore
from backend.store import SQLiteStore


PNG = b"\x89PNG\r\n\x1a\n" + b"backup-payload"


def media_database(path: Path, relative_path="media_1/original", payload=PNG):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('text-record-still-present')")
        connection.execute(
            """
            CREATE TABLE media (
                media_id TEXT PRIMARY KEY,
                relative_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                save_status TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO media VALUES (?, ?, ?, 'saved')",
            ("media_1", relative_path, hashlib.sha256(payload).hexdigest()),
        )


def media_metadata(path: Path):
    metadata = path / "media_1" / "metadata.json"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(
        '{"media_id":"media_1","kind":"image","content_type":"image/png",'
        '"size_bytes":22,"sha256":"metadata-test"}',
        encoding="utf-8",
    )


def test_media_bundle_restores_database_and_verified_originals(tmp_path):
    source_db = tmp_path / "records.sqlite3"
    source_media = tmp_path / "media"
    original = source_media / "media_1" / "original"
    original.parent.mkdir(parents=True)
    original.write_bytes(PNG)
    media_metadata(source_media)
    media_database(source_db)

    bundle = backup_media_bundle(source_db, source_media, tmp_path / "backup")
    restored_db = tmp_path / "restored" / "records.sqlite3"
    restored_media = tmp_path / "restored" / "media"
    result = restore_media_bundle(bundle, restored_db, restored_media)

    assert result == {"database": restored_db, "media_root": restored_media}
    assert (restored_media / "media_1" / "original").read_bytes() == PNG
    assert (restored_media / "media_1" / "metadata.json").is_file()
    with sqlite3.connect(restored_db) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == (
            "text-record-still-present"
        )
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["database"] == "records.sqlite3"
    item = manifest["media"][0]
    assert item["media_id"] == "media_1"
    assert item["relative_path"] == "media_1/original"
    assert item["sha256"] == hashlib.sha256(PNG).hexdigest()
    assert item["size_bytes"] == len(PNG)
    assert item["metadata_relative_path"] == "media_1/metadata.json"
    metadata = (source_media / "media_1" / "metadata.json").read_bytes()
    assert item["metadata_sha256"] == hashlib.sha256(metadata).hexdigest()
    assert item["metadata_size_bytes"] == len(metadata)


def test_real_media_store_can_read_after_bundle_restore(tmp_path):
    source_db = tmp_path / "real-records.sqlite3"
    source_root = tmp_path / "real-media"
    backend = LocalMediaBackend(SQLiteStore(source_db), source_root, recognition_provider="mock")
    payload = b"\x89PNG\r\n\x1a\nreal-media-backup"
    upload, _ = backend.create_upload(
        {
            "kind": "image",
            "content_type": "image/png",
            "total_parts": 1,
            "original_filename": "check.png",
        },
        "backup-real-create",
    )
    backend.write_part(upload["upload_id"], 0, payload, "backup-real-part")
    backend.complete_upload(upload["upload_id"], "backup-real-complete")

    bundle = backup_media_bundle(source_db, source_root, tmp_path / "real-backup")
    restored_db = tmp_path / "real-restored" / "records.sqlite3"
    restored_root = tmp_path / "real-restored" / "media"
    restore_media_bundle(bundle, restored_db, restored_root)

    store = MediaStore(restored_root)
    record = store.get_media(upload["media_id"])
    assert record.media_id == upload["media_id"]
    with store.open_original(upload["media_id"]) as stream:
        assert stream.read() == payload


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_restore_rejects_missing_or_corrupt_original_without_partial_output(
    tmp_path, damage
):
    source_db = tmp_path / "records.sqlite3"
    source_media = tmp_path / "media"
    original = source_media / "media_1" / "original"
    original.parent.mkdir(parents=True)
    original.write_bytes(PNG)
    media_metadata(source_media)
    media_database(source_db)
    bundle = backup_media_bundle(source_db, source_media, tmp_path / "backup")
    bundled_original = bundle / "media" / "media_1" / "original"
    if damage == "missing":
        bundled_original.unlink()
    else:
        bundled_original.write_bytes(PNG + b"tampered")

    restored_db = tmp_path / "restore" / "records.sqlite3"
    restored_media = tmp_path / "restore" / "media"
    with pytest.raises(ValueError, match="媒体原件.*(缺失|损坏)"):
        restore_media_bundle(bundle, restored_db, restored_media)

    assert not restored_db.exists()
    assert not restored_media.exists()


def test_backup_rejects_missing_or_changed_referenced_original(tmp_path):
    source_db = tmp_path / "records.sqlite3"
    source_media = tmp_path / "media"
    source_media.mkdir()
    media_database(source_db)

    with pytest.raises(ValueError, match="媒体原件缺失"):
        backup_media_bundle(source_db, source_media, tmp_path / "missing-backup")

    original = source_media / "media_1" / "original"
    original.parent.mkdir()
    original.write_bytes(PNG + b"not-the-database-hash")
    with pytest.raises(ValueError, match="媒体原件校验失败"):
        backup_media_bundle(source_db, source_media, tmp_path / "changed-backup")


def test_media_reference_cannot_escape_media_root(tmp_path):
    source_db = tmp_path / "records.sqlite3"
    source_media = tmp_path / "media"
    source_media.mkdir()
    outside = tmp_path / "outside-secret"
    outside.write_bytes(PNG)
    media_database(source_db, "../outside-secret")

    with pytest.raises(ValueError, match="媒体引用不安全"):
        backup_media_bundle(source_db, source_media, tmp_path / "backup")

    assert outside.read_bytes() == PNG


def test_bundle_and_restore_never_overwrite_existing_destinations(tmp_path):
    source_db = tmp_path / "records.sqlite3"
    source_media = tmp_path / "media"
    original = source_media / "media_1" / "original"
    original.parent.mkdir(parents=True)
    original.write_bytes(PNG)
    media_metadata(source_media)
    media_database(source_db)
    bundle = backup_media_bundle(source_db, source_media, tmp_path / "backup")

    with pytest.raises(ValueError, match="备份目标已存在"):
        backup_media_bundle(source_db, source_media, bundle)

    destination_db = tmp_path / "restored.sqlite3"
    destination_db.write_bytes(b"keep-me")
    with pytest.raises(ValueError, match="恢复目标已存在"):
        restore_media_bundle(bundle, destination_db, tmp_path / "restored-media")
    assert destination_db.read_bytes() == b"keep-me"


def test_legacy_database_only_backup_remains_unchanged(tmp_path):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE existing_text_data (value TEXT)")
        connection.execute("INSERT INTO existing_text_data VALUES ('kept')")

    target = backup(source, tmp_path / "legacy-backup.sqlite3")

    assert target.is_file()
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM existing_text_data").fetchone()[0] == (
            "kept"
        )
