"""Durable, path-safe storage for immutable uploaded media originals.

``MediaStore`` is the only filesystem seam callers need.  It owns server-side
identifiers, resumable binary parts, integrity checks, atomic publication and
safe reads.  It deliberately has no database or HTTP knowledge.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO


class MediaStoreError(RuntimeError):
    """A stable storage failure that does not expose local paths."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UploadNotFound(MediaStoreError):
    def __init__(self) -> None:
        super().__init__("upload_not_found", "上传任务不存在")


class MediaNotFound(MediaStoreError):
    def __init__(self) -> None:
        super().__init__("media_not_found", "媒体原件不存在")


class UploadConflict(MediaStoreError):
    def __init__(self, code: str = "upload_conflict", message: str = "上传内容冲突") -> None:
        super().__init__(code, message)


class UploadIncomplete(MediaStoreError):
    def __init__(self) -> None:
        super().__init__("upload_incomplete", "上传分片不完整")


@dataclass(frozen=True)
class UploadSession:
    upload_id: str
    media_id: str
    kind: str
    content_type: str
    total_parts: int
    expected_size: int | None
    expected_sha256: str | None
    original_filename: str | None
    created_at: str


@dataclass(frozen=True)
class MediaRecord:
    media_id: str
    kind: str
    content_type: str
    size_bytes: int
    sha256: str
    original_filename: str | None
    created_at: str


_ID_RE = re.compile(r"^(?:upload|media)_[0-9a-f]{32}$")
_AUDIO_TYPES = {
    "audio/aac",
    "audio/flac",
    "audio/m4a",
    "audio/mp3",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-m4a",
    "audio/x-wav",
}
_IMAGE_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _safe_id(value: object, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(prefix + "_")
        and _ID_RE.fullmatch(value) is not None
    )


def _normalise_content_type(kind: str, content_type: str) -> str:
    if kind not in {"audio", "image"} or not isinstance(content_type, str):
        raise MediaStoreError("unsupported_format", "不支持的媒体类型或格式")
    value = content_type.split(";", 1)[0].strip().lower()
    allowed = _AUDIO_TYPES if kind == "audio" else _IMAGE_TYPES
    if value not in allowed:
        raise MediaStoreError("unsupported_format", "不支持的媒体类型或格式")
    return value


def _looks_like_media(data: bytes, content_type: str) -> bool:
    if content_type in {"audio/wav", "audio/x-wav"}:
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    if content_type in {"audio/mp3", "audio/mpeg"}:
        return data.startswith(b"ID3") or (
            len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
        )
    if content_type == "audio/ogg":
        return data.startswith(b"OggS")
    if content_type == "audio/flac":
        return data.startswith(b"fLaC")
    if content_type in {"audio/mp4", "audio/m4a", "audio/x-m4a"}:
        return len(data) >= 12 and data[4:8] == b"ftyp"
    if content_type == "audio/webm":
        return data.startswith(b"\x1a\x45\xdf\xa3")
    if content_type == "audio/aac":
        return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xF6) == 0xF0
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if content_type == "image/tiff":
        return data.startswith((b"II*\x00", b"MM\x00*"))
    return False


def _write_json_atomic(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _open_regular_readonly(path: Path) -> BinaryIO:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError
        return os.fdopen(descriptor, "rb")
    except OSError:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        raise


def _read_json(path: Path) -> dict[str, object]:
    try:
        with _open_regular_readonly(path) as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise MediaStoreError("storage_corrupt", "媒体存储状态损坏") from None


class MediaStore:
    """Store resumable uploads and publish verified originals atomically.

    ``max_upload_bytes`` is an optional operational guardrail.  ``None`` means
    no store-level size limit; this module never imposes a product limit.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        max_upload_bytes: int | None = None,
        max_part_bytes: int | None = None,
        max_parts: int | None = None,
    ) -> None:
        if max_upload_bytes is not None and (
            type(max_upload_bytes) is not int or max_upload_bytes <= 0
        ):
            raise ValueError("max_upload_bytes must be a positive integer or None")
        if max_part_bytes is not None and (
            type(max_part_bytes) is not int or max_part_bytes <= 0
        ):
            raise ValueError("max_part_bytes must be a positive integer or None")
        if max_parts is not None and (
            type(max_parts) is not int or max_parts <= 0
        ):
            raise ValueError("max_parts must be a positive integer or None")
        requested_root = Path(root)
        if requested_root.exists() and requested_root.is_symlink():
            raise MediaStoreError("unsafe_storage", "媒体存储目录不安全")
        requested_root.mkdir(parents=True, exist_ok=True)
        if requested_root.is_symlink() or not requested_root.is_dir():
            raise MediaStoreError("unsafe_storage", "媒体存储目录不安全")
        self._root = requested_root.resolve()
        self._uploads = self._root / ".uploads"
        self._uploads.mkdir(mode=0o700, exist_ok=True)
        if self._uploads.is_symlink() or not self._uploads.is_dir():
            raise MediaStoreError("unsafe_storage", "媒体存储目录不安全")
        self._max_upload_bytes = max_upload_bytes
        self._max_part_bytes = max_part_bytes
        self._max_parts = max_parts
        self._lock = threading.RLock()
        self._clean_abandoned_temporaries()

    def create_upload(
        self,
        *,
        kind: str,
        content_type: str,
        total_parts: int,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
        original_filename: str | None = None,
        upload_id: str | None = None,
        media_id: str | None = None,
    ) -> UploadSession:
        """Create or recover a server-identified upload session.

        Trusted composition code may supply IDs already committed by the
        database. Repeating the same IDs and metadata recovers the same
        session; callers still cannot choose filesystem paths.
        """

        content_type = _normalise_content_type(kind, content_type)
        if type(total_parts) is not int or total_parts < 1:
            raise MediaStoreError("invalid_upload", "上传分片数量无效")
        if self._max_parts is not None and total_parts > self._max_parts:
            raise MediaStoreError("limit_exceeded", "媒体分片数量超过当前保护限制")
        if expected_size is not None and (
            type(expected_size) is not int or expected_size < 1
        ):
            raise MediaStoreError("invalid_upload", "预期文件大小无效")
        if (
            self._max_upload_bytes is not None
            and expected_size is not None
            and expected_size > self._max_upload_bytes
        ):
            raise MediaStoreError("limit_exceeded", "媒体超过当前存储保护限制")
        if expected_sha256 is not None:
            if not isinstance(expected_sha256, str) or re.fullmatch(
                r"[0-9a-fA-F]{64}", expected_sha256
            ) is None:
                raise MediaStoreError("invalid_upload", "预期摘要无效")
            expected_sha256 = expected_sha256.lower()
        if original_filename is not None and (
            not isinstance(original_filename, str)
            or "\x00" in original_filename
            or len(original_filename) > 1024
        ):
            raise MediaStoreError("invalid_upload", "原始文件名无效")
        if upload_id is not None and not _safe_id(upload_id, "upload"):
            raise MediaStoreError("invalid_upload", "上传任务编号无效")
        if media_id is not None and not _safe_id(media_id, "media"):
            raise MediaStoreError("invalid_upload", "媒体编号无效")
        if (upload_id is None) != (media_id is None):
            raise MediaStoreError("invalid_upload", "上传任务编号不完整")

        with self._lock:
            if upload_id is None:
                while True:
                    upload_id = _new_id("upload")
                    media_id = _new_id("media")
                    upload_dir = self._uploads / upload_id
                    media_dir = self._root / media_id
                    if not upload_dir.exists() and not media_dir.exists():
                        break
            else:
                upload_dir = self._uploads / upload_id
                media_dir = self._root / media_id
                if upload_dir.exists():
                    existing, _, _ = self._load_upload(upload_id)
                    requested = UploadSession(
                        upload_id=upload_id,
                        media_id=media_id,
                        kind=kind,
                        content_type=content_type,
                        total_parts=total_parts,
                        expected_size=expected_size,
                        expected_sha256=expected_sha256,
                        original_filename=original_filename,
                        created_at=existing.created_at,
                    )
                    if existing != requested:
                        raise UploadConflict()
                    return existing
                if media_dir.exists() or upload_dir.is_symlink() or media_dir.is_symlink():
                    raise UploadConflict()
            upload_dir.mkdir(mode=0o700)
            (upload_dir / "parts").mkdir(mode=0o700)
            session = UploadSession(
                upload_id=upload_id,
                media_id=media_id,
                kind=kind,
                content_type=content_type,
                total_parts=total_parts,
                expected_size=expected_size,
                expected_sha256=expected_sha256,
                original_filename=original_filename,
                created_at=_now(),
            )
            _write_json_atomic(
                upload_dir / "upload.json",
                {**asdict(session), "status": "uploading"},
            )
            return session

    def write_part(self, upload_id: str, index: int, data: bytes) -> None:
        """Write one numbered part; replaying identical bytes is idempotent."""

        if type(index) is not int:
            raise MediaStoreError("invalid_part", "上传分片编号无效")
        if not isinstance(data, bytes) or not data:
            raise MediaStoreError("invalid_part", "上传分片内容无效")
        if self._max_part_bytes is not None and len(data) > self._max_part_bytes:
            raise MediaStoreError("limit_exceeded", "媒体分片超过当前保护限制")
        with self._lock:
            session, status, upload_dir = self._load_upload(upload_id)
            if status == "completed":
                raise UploadConflict("upload_completed", "上传任务已经完成")
            if index < 0 or index >= session.total_parts:
                raise MediaStoreError("invalid_part", "上传分片编号无效")
            parts_dir = upload_dir / "parts"
            self._require_safe_directory(parts_dir)
            destination = parts_dir / f"{index:08d}.part"
            if destination.exists() or destination.is_symlink():
                if destination.is_symlink() or not destination.is_file():
                    raise MediaStoreError("unsafe_storage", "媒体存储目录不安全")
                if self._same_file_bytes(destination, data):
                    return
                raise UploadConflict()
            if self._max_upload_bytes is not None:
                current_size = self._parts_size(parts_dir)
                if current_size + len(data) > self._max_upload_bytes:
                    raise MediaStoreError(
                        "limit_exceeded", "媒体超过当前存储保护限制"
                    )
            temporary = parts_dir / f".part-tmp-{uuid.uuid4().hex}"
            try:
                with temporary.open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, destination)
            except OSError:
                raise MediaStoreError("storage_failed", "上传分片保存失败") from None
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    def complete(self, upload_id: str) -> MediaRecord:
        """Validate all parts and atomically publish one immutable original."""

        with self._lock:
            session, status, upload_dir = self._load_upload(upload_id)
            if status == "completed":
                parts_dir = upload_dir / "parts"
                if parts_dir.is_dir() and not parts_dir.is_symlink():
                    self._discard_parts(parts_dir)
                return self.get_media(session.media_id)
            parts_dir = upload_dir / "parts"
            self._require_safe_directory(parts_dir)
            expected_names = [f"{index:08d}.part" for index in range(session.total_parts)]
            for name in expected_names:
                part = parts_dir / name
                if part.is_symlink() or not part.is_file():
                    raise UploadIncomplete()

            final_dir = self._root / session.media_id
            if final_dir.exists() or final_dir.is_symlink():
                record = self.get_media(session.media_id)
                self._mark_completed(upload_dir, session)
                self._discard_parts(parts_dir)
                return record

            publishing = self._root / f".publishing-{uuid.uuid4().hex}"
            try:
                publishing.mkdir(mode=0o700)
                original = publishing / "original"
                digest = hashlib.sha256()
                size = 0
                header = bytearray()
                with original.open("xb") as target:
                    for name in expected_names:
                        with _open_regular_readonly(parts_dir / name) as source:
                            while True:
                                chunk = source.read(1024 * 1024)
                                if not chunk:
                                    break
                                target.write(chunk)
                                digest.update(chunk)
                                size += len(chunk)
                                if len(header) < 16:
                                    header.extend(chunk[: 16 - len(header)])
                                if (
                                    self._max_upload_bytes is not None
                                    and size > self._max_upload_bytes
                                ):
                                    raise MediaStoreError(
                                        "limit_exceeded",
                                        "媒体超过当前存储保护限制",
                                    )
                    target.flush()
                    os.fsync(target.fileno())
                sha256 = digest.hexdigest()
                if size < 1 or not _looks_like_media(bytes(header), session.content_type):
                    raise MediaStoreError("invalid_media", "媒体内容与声明格式不符")
                if session.expected_size is not None and size != session.expected_size:
                    raise MediaStoreError("integrity_mismatch", "媒体完整性校验失败")
                if (
                    session.expected_sha256 is not None
                    and sha256 != session.expected_sha256
                ):
                    raise MediaStoreError("integrity_mismatch", "媒体完整性校验失败")
                record = MediaRecord(
                    media_id=session.media_id,
                    kind=session.kind,
                    content_type=session.content_type,
                    size_bytes=size,
                    sha256=sha256,
                    original_filename=session.original_filename,
                    created_at=_now(),
                )
                os.chmod(original, 0o400)
                _write_json_atomic(publishing / "metadata.json", asdict(record))
                os.rename(publishing, final_dir)
            except MediaStoreError:
                self._remove_private_tree(publishing)
                raise
            except OSError:
                self._remove_private_tree(publishing)
                raise MediaStoreError("storage_failed", "媒体原件保存失败") from None

            self._mark_completed(upload_dir, session)
            self._discard_parts(parts_dir)
            return record

    def get_media(self, media_id: str) -> MediaRecord:
        """Return persisted metadata for a completed media original."""

        if not _safe_id(media_id, "media"):
            raise MediaNotFound()
        media_dir = self._root / media_id
        if media_dir.is_symlink() or not media_dir.is_dir():
            raise MediaNotFound()
        value = _read_json(media_dir / "metadata.json")
        try:
            record = MediaRecord(**value)
        except (TypeError, ValueError):
            raise MediaStoreError("storage_corrupt", "媒体存储状态损坏") from None
        if record.media_id != media_id:
            raise MediaStoreError("storage_corrupt", "媒体存储状态损坏")
        return record

    def open_original(self, media_id: str) -> BinaryIO:
        """Open a verified original read-only, addressed only by ``media_id``."""

        record = self.get_media(media_id)
        path = self._root / media_id / "original"
        try:
            stream = _open_regular_readonly(path)
            if os.fstat(stream.fileno()).st_size != record.size_bytes:
                raise OSError
            digest = hashlib.sha256()
            header = bytearray()
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                if len(header) < 16:
                    header.extend(chunk[: 16 - len(header)])
            if digest.hexdigest() != record.sha256 or not _looks_like_media(
                bytes(header), record.content_type
            ):
                raise OSError
            stream.seek(0)
            return stream
        except OSError:
            try:
                stream.close()
            except (OSError, UnboundLocalError):
                pass
            raise MediaStoreError("integrity_mismatch", "媒体完整性校验失败") from None

    def get_original_path(self, media_id: str) -> Path:
        """Return the verified server-owned path used by recognition adapters."""

        with self.open_original(media_id):
            pass
        return self._root / media_id / "original"

    def _load_upload(self, upload_id: str) -> tuple[UploadSession, str, Path]:
        if not _safe_id(upload_id, "upload"):
            raise UploadNotFound()
        upload_dir = self._uploads / upload_id
        if upload_dir.is_symlink() or not upload_dir.is_dir():
            raise UploadNotFound()
        value = _read_json(upload_dir / "upload.json")
        status = value.pop("status", None)
        if status not in {"uploading", "completed"}:
            raise MediaStoreError("storage_corrupt", "媒体存储状态损坏")
        try:
            session = UploadSession(**value)
        except (TypeError, ValueError):
            raise MediaStoreError("storage_corrupt", "媒体存储状态损坏") from None
        if session.upload_id != upload_id or not _safe_id(session.media_id, "media"):
            raise MediaStoreError("storage_corrupt", "媒体存储状态损坏")
        return session, status, upload_dir

    def _mark_completed(self, upload_dir: Path, session: UploadSession) -> None:
        _write_json_atomic(
            upload_dir / "upload.json",
            {**asdict(session), "status": "completed"},
        )

    @staticmethod
    def _same_file_bytes(path: Path, data: bytes) -> bool:
        try:
            with _open_regular_readonly(path) as stream:
                if os.fstat(stream.fileno()).st_size != len(data):
                    return False
                return stream.read() == data
        except OSError:
            raise MediaStoreError("storage_failed", "上传分片读取失败") from None

    @staticmethod
    def _require_safe_directory(path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise MediaStoreError("unsafe_storage", "媒体存储目录不安全")

    @staticmethod
    def _parts_size(parts_dir: Path) -> int:
        total = 0
        try:
            for path in parts_dir.iterdir():
                if path.name.endswith(".part"):
                    with _open_regular_readonly(path) as stream:
                        total += os.fstat(stream.fileno()).st_size
            return total
        except OSError:
            raise MediaStoreError("storage_failed", "上传分片读取失败") from None

    @staticmethod
    def _discard_parts(parts_dir: Path) -> None:
        try:
            for path in parts_dir.iterdir():
                if path.is_symlink() or path.is_file():
                    path.unlink()
            parts_dir.rmdir()
        except OSError:
            # Publication already succeeded; cleanup must never turn success
            # into a false failure. A later process can safely retry cleanup.
            return

    @staticmethod
    def _remove_private_tree(path: Path) -> None:
        try:
            if path.is_symlink():
                path.unlink()
            elif path.exists():
                shutil.rmtree(path)
        except OSError:
            return

    def _clean_abandoned_temporaries(self) -> None:
        try:
            for path in self._root.iterdir():
                if path.name.startswith(".publishing-"):
                    self._remove_private_tree(path)
            for upload_dir in self._uploads.iterdir():
                if upload_dir.is_symlink() or not upload_dir.is_dir():
                    continue
                parts_dir = upload_dir / "parts"
                if parts_dir.is_symlink() or not parts_dir.is_dir():
                    continue
                for path in parts_dir.iterdir():
                    if path.name.startswith(".part-tmp-"):
                        if path.is_symlink() or path.is_file():
                            path.unlink()
        except OSError:
            raise MediaStoreError("storage_failed", "媒体临时文件清理失败") from None


__all__ = [
    "MediaNotFound",
    "MediaRecord",
    "MediaStore",
    "MediaStoreError",
    "UploadConflict",
    "UploadIncomplete",
    "UploadNotFound",
    "UploadSession",
]
