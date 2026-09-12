import pytest

from backend.store import Conflict, SQLiteStore


def upload_payload(**overrides):
    payload = {
        "kind": "audio",
        "content_type": "audio/wav",
        "original_filename": "voice.wav",
        "expected_parts": 2,
    }
    payload.update(overrides)
    return payload


def test_upload_metadata_is_idempotent_and_queryable(tmp_path):
    store = SQLiteStore(tmp_path / "records.sqlite3")

    media, created = store.create_media_upload(upload_payload(), "upload-1")
    replay, replay_created = store.create_media_upload(upload_payload(), "upload-1")

    assert created is True
    assert replay_created is False
    assert replay == media
    assert media["media_id"].startswith("media_")
    assert media["upload_id"].startswith("upload_")
    assert media["save_status"] == "uploading"
    assert media["recognition_status"] == "not_started"
    assert media["link_status"] == "not_linked"
    assert media["version"] == 1
    assert media["size_bytes"] is None
    assert media["sha256"] is None
    assert "relative_path" not in media
    assert store.get_media(media["media_id"]) == media
    assert store.list_media() == [media]

    with pytest.raises(Conflict, match="^idempotency_key_payload_mismatch$"):
        store.create_media_upload(
            upload_payload(original_filename="different.wav"),
            "upload-1",
        )
