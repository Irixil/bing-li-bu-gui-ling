import hashlib
from pathlib import Path

import pytest

from backend.media_store import (
    MediaNotFound,
    MediaStore,
    MediaStoreError,
    UploadConflict,
    UploadIncomplete,
    UploadNotFound,
)


PNG = b"\x89PNG\r\n\x1a\n" + b"png-payload"
WAV = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"wav-payload"


def store(tmp_path: Path, **kwargs) -> MediaStore:
    return MediaStore(tmp_path / "media", **kwargs)


def test_complete_writes_ordered_parts_and_returns_verified_metadata(tmp_path):
    media_store = store(tmp_path)
    session = media_store.create_upload(
        kind="audio",
        content_type="audio/wav",
        total_parts=3,
        expected_size=len(WAV),
        expected_sha256=hashlib.sha256(WAV).hexdigest(),
        original_filename="老人录音.wav",
    )

    media_store.write_part(session.upload_id, 2, WAV[8:])
    media_store.write_part(session.upload_id, 0, WAV[:4])
    media_store.write_part(session.upload_id, 1, WAV[4:8])

    record = media_store.complete(session.upload_id)

    assert record.media_id == session.media_id
    assert record.kind == "audio"
    assert record.content_type == "audio/wav"
    assert record.original_filename == "老人录音.wav"
    assert record.size_bytes == len(WAV)
    assert record.sha256 == hashlib.sha256(WAV).hexdigest()
    with media_store.open_original(record.media_id) as original:
        assert original.read() == WAV


def test_duplicate_part_with_same_bytes_is_idempotent(tmp_path):
    media_store = store(tmp_path)
    session = media_store.create_upload(
        kind="image", content_type="image/png", total_parts=1
    )

    media_store.write_part(session.upload_id, 0, PNG)
    media_store.write_part(session.upload_id, 0, PNG)
    record = media_store.complete(session.upload_id)

    assert record.size_bytes == len(PNG)
    with media_store.open_original(record.media_id) as original:
        assert original.read() == PNG


def test_duplicate_part_with_different_bytes_is_rejected(tmp_path):
    media_store = store(tmp_path)
    session = media_store.create_upload(
        kind="image", content_type="image/png", total_parts=1
    )
    media_store.write_part(session.upload_id, 0, PNG)

    with pytest.raises(UploadConflict):
        media_store.write_part(session.upload_id, 0, PNG + b"changed")


def test_complete_rejects_missing_parts_without_publishing_original(tmp_path):
    media_store = store(tmp_path)
    session = media_store.create_upload(
        kind="audio", content_type="audio/wav", total_parts=2
    )
    media_store.write_part(session.upload_id, 1, WAV)

    with pytest.raises(UploadIncomplete):
        media_store.complete(session.upload_id)

    with pytest.raises(MediaNotFound):
        media_store.open_original(session.media_id)


@pytest.mark.parametrize(
    ("kind", "content_type", "payload"),
    [
        ("audio", "audio/wav", PNG),
        ("image", "image/png", WAV),
        ("image", "image/jpeg", PNG),
    ],
)
def test_complete_rejects_corrupt_or_falsified_mime(tmp_path, kind, content_type, payload):
    media_store = store(tmp_path)
    session = media_store.create_upload(
        kind=kind, content_type=content_type, total_parts=1
    )
    media_store.write_part(session.upload_id, 0, payload)

    with pytest.raises(MediaStoreError) as exc_info:
        media_store.complete(session.upload_id)

    assert exc_info.value.code == "invalid_media"
    with pytest.raises(MediaNotFound):
        media_store.open_original(session.media_id)


def test_expected_hash_and_size_are_verified_without_truncating_input(tmp_path):
    media_store = store(tmp_path)
    session = media_store.create_upload(
        kind="image",
        content_type="image/png",
        total_parts=1,
        expected_size=len(PNG) + 1,
        expected_sha256=hashlib.sha256(PNG + b"different").hexdigest(),
    )
    media_store.write_part(session.upload_id, 0, PNG)

    with pytest.raises(MediaStoreError) as exc_info:
        media_store.complete(session.upload_id)

    assert exc_info.value.code == "integrity_mismatch"
    with pytest.raises(MediaNotFound):
        media_store.open_original(session.media_id)


def test_protection_limit_is_explicit_and_does_not_apply_by_default(tmp_path):
    unrestricted = store(tmp_path / "unrestricted")
    session = unrestricted.create_upload(
        kind="image", content_type="image/png", total_parts=1
    )
    unrestricted.write_part(session.upload_id, 0, PNG)
    assert unrestricted.complete(session.upload_id).size_bytes == len(PNG)

    limited = store(tmp_path / "limited", max_upload_bytes=len(PNG) - 1)
    limited_session = limited.create_upload(
        kind="image", content_type="image/png", total_parts=1
    )
    with pytest.raises(MediaStoreError) as exc_info:
        limited.write_part(limited_session.upload_id, 0, PNG)
    assert exc_info.value.code == "limit_exceeded"


def test_client_paths_and_symlink_like_ids_cannot_escape_storage_root(tmp_path):
    media_store = store(tmp_path)

    with pytest.raises(MediaStoreError):
        media_store.write_part("../outside", 0, PNG)
    with pytest.raises(UploadNotFound):
        media_store.complete("../../etc/passwd")
    with pytest.raises(MediaNotFound):
        media_store.open_original("../outside")

    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"must stay unchanged")
    assert outside.read_bytes() == b"must stay unchanged"


def test_original_filename_is_metadata_only_and_never_selects_storage_path(tmp_path):
    media_store = store(tmp_path)
    session = media_store.create_upload(
        kind="image",
        content_type="image/png",
        total_parts=1,
        original_filename="../../outside.png",
    )
    media_store.write_part(session.upload_id, 0, PNG)

    record = media_store.complete(session.upload_id)

    assert record.original_filename == "../../outside.png"
    assert not (tmp_path / "outside.png").exists()
    with media_store.open_original(record.media_id) as original:
        assert original.read() == PNG


def test_part_symlink_is_rejected_without_touching_its_target(tmp_path):
    root = tmp_path / "media"
    media_store = MediaStore(root)
    session = media_store.create_upload(
        kind="image", content_type="image/png", total_parts=1
    )
    outside = tmp_path / "outside.part"
    outside.write_bytes(b"must stay unchanged")
    part_path = root / ".uploads" / session.upload_id / "parts" / "00000000.part"
    part_path.symlink_to(outside)

    with pytest.raises(MediaStoreError) as exc_info:
        media_store.write_part(session.upload_id, 0, PNG)

    assert exc_info.value.code == "unsafe_storage"
    assert outside.read_bytes() == b"must stay unchanged"


def test_safe_read_rejects_an_original_replaced_by_a_symlink(tmp_path):
    root = tmp_path / "media"
    media_store = MediaStore(root)
    session = media_store.create_upload(
        kind="image", content_type="image/png", total_parts=1
    )
    media_store.write_part(session.upload_id, 0, PNG)
    record = media_store.complete(session.upload_id)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    original_path = root / record.media_id / "original"
    original_path.unlink()
    original_path.symlink_to(outside)

    with pytest.raises(MediaStoreError) as exc_info:
        media_store.open_original(record.media_id)

    assert exc_info.value.code == "integrity_mismatch"
    assert outside.read_bytes() == PNG


def test_reopen_preserves_valid_parts_and_cleans_abandoned_temporaries(tmp_path):
    root = tmp_path / "media"
    media_store = MediaStore(root)
    session = media_store.create_upload(
        kind="audio", content_type="audio/wav", total_parts=2
    )
    media_store.write_part(session.upload_id, 0, WAV[:8])
    stale_part = (
        root
        / ".uploads"
        / session.upload_id
        / "parts"
        / ".part-tmp-interrupted"
    )
    stale_part.write_bytes(b"incomplete")
    stale_publish = root / ".publishing-interrupted"
    stale_publish.mkdir()
    (stale_publish / "original").write_bytes(b"incomplete")

    reopened = MediaStore(root)

    assert not stale_part.exists()
    assert not stale_publish.exists()
    reopened.write_part(session.upload_id, 1, WAV[8:])
    record = reopened.complete(session.upload_id)
    with reopened.open_original(record.media_id) as original:
        assert original.read() == WAV


def test_original_is_immutable_through_store_and_survives_reopen(tmp_path):
    media_store = store(tmp_path)
    session = media_store.create_upload(
        kind="image", content_type="image/png", total_parts=1
    )
    media_store.write_part(session.upload_id, 0, PNG)
    record = media_store.complete(session.upload_id)
    before = record.sha256

    with pytest.raises(MediaStoreError):
        media_store.write_part(session.upload_id, 0, PNG + b"late")

    reopened = MediaStore(tmp_path / "media")
    assert reopened.get_media(record.media_id) == record
    with reopened.open_original(record.media_id) as original:
        assert original.read() == PNG
    assert reopened.get_original_path(record.media_id).name == "original"
    assert reopened.get_media(record.media_id).sha256 == before


def test_unknown_upload_and_media_ids_have_stable_failures(tmp_path):
    media_store = store(tmp_path)

    with pytest.raises(UploadNotFound):
        media_store.write_part("upload_missing", 0, PNG)
    with pytest.raises(UploadNotFound):
        media_store.complete("upload_missing")
    with pytest.raises(MediaNotFound):
        media_store.get_media("media_missing")
