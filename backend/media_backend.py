"""Compose filesystem, SQLite, and recognition into one local media module."""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .media_service import MediaRecognitionService
from .media_store import MediaStore
from .store import Conflict, NotFound, SQLiteStore


class LocalMediaBackend:
    """Expose the narrow interface consumed by the HTTP handler.

    Filesystem publication and SQLite commits cannot be one transaction. The
    ordering here prevents false "saved" responses: an original is published
    first, and media becomes publicly saved only after its metadata commits.
    Idempotent replays repair the safe crash windows.
    """

    def __init__(
        self,
        event_store: SQLiteStore,
        media_root: str | os.PathLike[str],
        *,
        max_upload_bytes: int | None = None,
        max_part_bytes: int | None = None,
        max_parts: int | None = None,
        recognition_provider: str | None = None,
        background: bool = False,
        workers: int = 2,
    ) -> None:
        self.event_store = event_store
        self.file_store = MediaStore(
            media_root,
            max_upload_bytes=max_upload_bytes,
            max_part_bytes=max_part_bytes,
            max_parts=max_parts,
        )
        self.recognition_provider = recognition_provider
        self.background = background
        self._recognition = MediaRecognitionService(event_store, self.file_store)
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="media-recognition",
        )
        self._lock = RLock()

    @staticmethod
    def _household(household_id: str | None) -> str:
        return household_id or "hh_local_default"

    def create_upload(
        self,
        metadata: Mapping[str, Any],
        idempotency_key: str,
        household_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        payload = dict(metadata)
        database_media, created = self.event_store.create_media_upload(
            payload,
            idempotency_key,
            self._household(household_id),
        )
        try:
            session = self.file_store.create_upload(
                kind=database_media["kind"],
                content_type=database_media["content_type"],
                total_parts=database_media["expected_parts"],
                expected_size=database_media.get("expected_size"),
                expected_sha256=database_media.get("expected_sha256"),
                original_filename=database_media.get("original_filename"),
                upload_id=database_media["upload_id"],
                media_id=database_media["media_id"],
            )
        except Exception:
            # The database row remains an honest, recoverable uploading state.
            raise
        return {**asdict(session), "status": "uploading"}, created

    def write_part(
        self,
        upload_id: str,
        index: int,
        payload: bytes,
        idempotency_key: str,
        household_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        with self._lock:
            media_before = self._media_for_upload(upload_id, household_id)
            before_parts = media_before["uploaded_parts"]
            self.file_store.write_part(upload_id, index, payload)
            relative_path = f".uploads/{upload_id}/parts/{index:08d}.part"
            try:
                part, created = self.event_store.record_media_part(
                    upload_id,
                    index,
                    relative_path=relative_path,
                    size_bytes=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    idempotency_key=idempotency_key,
                )
            except Exception:
                # An identical retry reconciles a part saved before the DB write.
                raise
            if not created and before_parts == 0:
                created = False
            return {
                "upload_id": part["upload_id"],
                "index": part["index"],
                "size_bytes": part["size_bytes"],
            }, created

    def complete_upload(
        self,
        upload_id: str,
        idempotency_key: str,
        household_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        self._media_for_upload(upload_id, household_id)
        original = self.file_store.complete(upload_id)
        media, created = self.event_store.complete_media_upload(
            upload_id,
            size_bytes=original.size_bytes,
            sha256=original.sha256,
            relative_path=f"{original.media_id}/original",
            content_type=original.content_type,
            saved_at=original.created_at,
            idempotency_key=idempotency_key,
        )
        return media, created

    def list_media(self, household_id: str | None = None) -> list[dict[str, Any]]:
        return self.event_store.list_media(household_id)

    def get_media(
        self, media_id: str, household_id: str | None = None
    ) -> dict[str, Any] | None:
        return self.event_store.get_media(media_id, household_id)

    def open_original(self, media_id: str, household_id: str | None = None):
        media = self.event_store.get_media(media_id, household_id)
        if media is None or media["save_status"] != "saved":
            raise NotFound("media_not_found")
        return self.file_store.open_original(media_id)

    def start_recognition(
        self,
        media_id: str,
        expected_version: int,
        idempotency_key: str,
        *,
        actor: str,
        household_id: str | None = None,
    ) -> dict[str, Any]:
        media = self.event_store.get_media(media_id, household_id)
        if media is None:
            raise NotFound("media_not_found")
        claim = dict(
            self.event_store.claim_media_recognition(
                media_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                actor=actor,
            )
        )
        if claim.get("action") != "claimed":
            return claim
        if self.background:
            self._executor.submit(
                self._recognition.process_claimed,
                claim,
                actor=actor,
                provider=self.recognition_provider,
            )
            return claim
        return self._recognition.process_claimed(
            claim,
            actor=actor,
            provider=self.recognition_provider,
        )

    def link_media(
        self,
        media_id: str,
        idempotency_key: str,
        expected_version: int | None = None,
        *,
        actor: str,
        household_id: str | None = None,
    ) -> dict[str, Any]:
        """Link the persisted successful transcript without recognizing again."""

        media = self.event_store.get_media(media_id, household_id)
        if media is None:
            raise NotFound("media_not_found")
        attempt = media.get("latest_attempt")
        if not attempt or attempt.get("status") != "succeeded":
            raise Conflict("recognition_not_succeeded")
        return self.event_store.create_and_link_media_event(
            media_id,
            attempt["attempt_id"],
            payload={"related_record_ids": []},
            idempotency_key=idempotency_key,
            actor=actor,
            household_id=media["household_id"],
            expected_version=expected_version,
        )

    def _media_for_upload(
        self, upload_id: str, household_id: str | None
    ) -> dict[str, Any]:
        for media in self.event_store.list_media(household_id):
            if media.get("upload_id") == upload_id:
                return media
        raise NotFound("upload_not_found")


def create_default_media_backend(
    event_store: SQLiteStore,
    *,
    root: str | os.PathLike[str],
) -> LocalMediaBackend:
    def positive(name: str) -> int | None:
        value = os.getenv(name)
        return int(value) if value and value.isdigit() and int(value) > 0 else None

    return LocalMediaBackend(
        event_store,
        Path(root),
        max_upload_bytes=positive("MEDIA_UPLOAD_MAX_BYTES"),
        max_part_bytes=positive("MEDIA_UPLOAD_PART_MAX_BYTES"),
        max_parts=positive("MEDIA_UPLOAD_MAX_PARTS"),
        # Mock is an explicit offline choice. A missing provider must remain
        # distinguishable from Mock and surface provider_not_configured.
        # Resolve per-kind provider overrides at recognition time. An explicit
        # LocalMediaBackend(recognition_provider=...) remains an explicit override.
        recognition_provider=None,
        background=True,
    )


__all__ = ["LocalMediaBackend", "create_default_media_backend"]
