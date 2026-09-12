"""Local ASR/OCR adapters for already-persisted media.

This module deliberately has no database or HTTP responsibilities.  The caller
hands it an immutable local file and receives either a complete machine draft
or a stable, safe error.  Event creation, retries and safety scanning belong to
the integration owner (task A).

The default providers are local and do not upload health data:

* ASR: OpenAI Whisper through the configured Python interpreter.
* OCR: Apple's Vision framework through the small helper compiled from
  ``tools/media-recognition/vision_ocr.swift``.

Both providers are explicit.  Missing local tools do not silently become Mock
results or a different cloud provider.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VISION_BINARY = ROOT / "tools" / "media-recognition" / "vision_ocr"
DEFAULT_WHISPER_RUNNER = ROOT / "tools" / "media-recognition" / "whisper_runner.py"

SUPPORTED_AUDIO = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/ogg",
    "audio/flac",
    "audio/webm",
}
SUPPORTED_IMAGES = {
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "image/heic",
    "image/heif",
}


def _signature_matches(path: Path, mime: str) -> bool:
    """Reject obvious content-type spoofing before invoking a provider.

    This is intentionally a small magic-byte check, not a decoder.  The
    provider still performs the authoritative decode and may return
    ``invalid_media`` for a truncated or otherwise damaged file.
    """
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return False
    if mime in {"audio/wav", "audio/x-wav"}:
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if mime in {"audio/mpeg", "audio/mp3"}:
        return head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
    if mime == "audio/flac":
        return head.startswith(b"fLaC")
    if mime == "audio/ogg":
        return head.startswith(b"OggS")
    if mime in {"audio/mp4", "audio/x-m4a"}:
        return len(head) >= 8 and head[4:8] == b"ftyp"
    if mime == "audio/webm":
        return head.startswith(b"\x1a\x45\xdf\xa3")
    if mime == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if mime in {"image/jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if mime in {"image/tiff"}:
        return head.startswith((b"II*\x00", b"MM\x00*"))
    # HEIC/HEIF and WebP are handed to the OS decoder; their signatures vary
    # by brand and are not safely inferred from a short prefix here.
    return True


@dataclass(frozen=True)
class RecognitionResult:
    """Machine-produced text; no confidence is invented."""

    text: str
    provider: str
    model: str | None
    is_mock: bool = False
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "is_mock": self.is_mock,
        }
        if self.warnings:
            result["warnings"] = list(self.warnings)
        return result


class RecognitionError(RuntimeError):
    """A safe, stable error for the A-side task runner to persist."""

    def __init__(self, code: str, message: str, retryable: bool):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


def _safe_kind(kind: Any) -> str:
    value = str(kind or "").strip().lower()
    if value in {"asr", "audio", "speech", "audio_transcript"}:
        return "audio"
    if value in {"ocr", "image", "photo", "document"}:
        return "image"
    raise RecognitionError("unsupported_media_kind", "媒体种类不受支持。", False)


def _safe_content_type(path: Path, content_type: Any) -> str:
    value = str(content_type or "").split(";", 1)[0].strip().lower()
    if value:
        return value
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _validate_file(path: str | os.PathLike[str], kind: str, content_type: Any) -> tuple[Path, str]:
    # Resolve only for validation and execution; the returned value is never
    # exposed to the caller or included in a public error message.
    try:
        file_path = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise RecognitionError("invalid_media", "媒体文件不存在或无法读取。", False)
    if not file_path.is_file():
        raise RecognitionError("invalid_media", "媒体文件不存在或无法读取。", False)
    try:
        size = file_path.stat().st_size
    except OSError:
        raise RecognitionError("invalid_media", "媒体文件无法读取。", False)
    if size <= 0:
        raise RecognitionError("invalid_media", "媒体文件为空。", False)
    # These are deliberately conservative adapter guardrails, not a product
    # upload contract.  A must publish the final limits in the media API.
    max_bytes = int(os.getenv("MEDIA_RECOGNITION_MAX_BYTES", str(50 * 1024 * 1024)))
    if size > max_bytes:
        raise RecognitionError("limit_exceeded", "媒体文件超过当前识别适配器限制。", False)
    mime = _safe_content_type(file_path, content_type)
    accepted = SUPPORTED_AUDIO if kind == "audio" else SUPPORTED_IMAGES
    if mime not in accepted:
        raise RecognitionError("unsupported_format", "媒体格式不受当前识别适配器支持。", False)
    if not _signature_matches(file_path, mime):
        raise RecognitionError("invalid_media", "媒体内容与声明格式不匹配或已损坏。", False)
    return file_path, mime


def _provider_name(kind: str) -> str:
    key = "MEDIA_ASR_PROVIDER" if kind == "audio" else "MEDIA_OCR_PROVIDER"
    return os.getenv(key, "local").strip().lower()


def _run_json_command(command: list[str], timeout: float) -> Mapping[str, Any]:
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RecognitionError("provider_timeout", "识别服务超时，可稍后重试。", True) from exc
    except OSError as exc:
        raise RecognitionError("provider_unavailable", "本地识别服务不可用。", True) from exc
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        # A non-zero process with no safe JSON classification is still an
        # unavailable provider.  Never expose stderr or the command line.
        if completed.returncode != 0:
            raise RecognitionError("provider_unavailable", "本地识别服务返回失败，可稍后重试。", True) from exc
        raise RecognitionError("invalid_provider_response", "识别服务返回格式无效。", True) from exc
    if not isinstance(payload, Mapping):
        raise RecognitionError("invalid_provider_response", "识别服务返回格式无效。", True)
    if payload.get("ok") is not True:
        error_code = str(payload.get("error_code") or "provider_unavailable")
        if error_code not in {
            "provider_not_configured",
            "unsupported_format",
            "invalid_media",
            "limit_exceeded",
            "no_text_detected",
            "provider_timeout",
            "provider_unavailable",
            "provider_auth_failed",
            "provider_rate_limited",
            "invalid_provider_response",
        }:
            error_code = "provider_unavailable"
        raise RecognitionError(error_code, "识别服务未返回可用文字。", error_code in {
            "provider_timeout", "provider_unavailable", "provider_rate_limited"
        })
    return payload


def _recognize_dashscope_audio(path: Path, mime: str, attempt_id: str, *, model_override: str | None = None) -> RecognitionResult:
    """Call DashScope's OpenAI-compatible audio transcription endpoint.

    The file is already persisted locally. This provider uploads it only when
    explicitly selected with MEDIA_ASR_PROVIDER=dashscope; it never becomes a
    silent fallback.
    """
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise RecognitionError("provider_not_configured", "未配置 DASHSCOPE_API_KEY。", False)
    model = (model_override or os.getenv("DASHSCOPE_ASR_MODEL", "qwen3-asr-flash")).strip() or "qwen3-asr-flash"
    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    timeout = float(os.getenv("MEDIA_ASR_TIMEOUT_SECONDS", os.getenv("MEDIA_RECOGNITION_TIMEOUT_SECONDS", "180")))
    boundary = "----codex-" + secrets.token_hex(12)
    data = path.read_bytes()
    parts: list[bytes] = []
    def field(name: str, value: str) -> None:
        parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"])
    field("model", model)
    parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(), f"Content-Type: {mime}\r\n\r\n".encode(), data, b"\r\n", f"--{boundary}--\r\n".encode()])
    req = urllib.request.Request(
        base_url + "/audio/transcriptions",
        data=b"".join(parts),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        code = "provider_auth_failed" if exc.code in {401, 403} else "provider_rate_limited" if exc.code == 429 else "provider_unavailable"
        raise RecognitionError(code, "云端 ASR 请求失败。", code in {"provider_rate_limited", "provider_unavailable"}) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RecognitionError("provider_timeout" if isinstance(exc, TimeoutError) else "provider_unavailable", "云端 ASR 暂时不可用，可稍后重试。", True) from exc
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise RecognitionError("invalid_provider_response", "云端 ASR 返回格式无效。", True)
    return RecognitionResult(text=text.strip(), provider="dashscope", model=model, is_mock=False)


def _recognize_audio(path: Path, mime: str, attempt_id: str) -> RecognitionResult:
    provider = _provider_name("audio")
    if provider in {"mock", "test"}:
        raise RecognitionError("mock_provider_not_allowed", "识别模块不在生产调用中自动使用 Mock。", False)
    if provider in {"dashscope", "aliyun", "aliyun-asr", "qwen", "qwen3-asr-flash", "paraformer"}:
        # The model is explicit for the comparison run.  In particular,
        # selecting paraformer must not mutate process-wide environment state
        # or accidentally inherit a previously selected Qwen model.
        model_override = "paraformer-v2" if provider == "paraformer" else None
        return _recognize_dashscope_audio(path, mime, attempt_id, model_override=model_override)
    if provider not in {"local", "whisper", "whisper-local"}:
        raise RecognitionError("provider_not_configured", "当前未配置支持的 ASR 服务。", False)
    python_bin = os.getenv("WHISPER_PYTHON", sys.executable)
    runner = Path(os.getenv("WHISPER_RUNNER", str(DEFAULT_WHISPER_RUNNER))).expanduser()
    if not runner.is_file():
        raise RecognitionError("provider_not_configured", "本地 Whisper 运行器不存在。", False)
    # ``base`` is the default because the first local Chinese smoke test
    # showed that ``tiny`` can drop or substitute characters.  Deployments may
    # choose a larger model after evaluating latency and device memory.
    model = os.getenv("WHISPER_MODEL", "base").strip() or "base"
    timeout = float(os.getenv("MEDIA_ASR_TIMEOUT_SECONDS", os.getenv("MEDIA_RECOGNITION_TIMEOUT_SECONDS", "180")))
    payload = _run_json_command(
        [python_bin, str(runner), str(path), model, "zh", attempt_id], timeout
    )
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RecognitionError("no_text_detected", "录音中没有识别到可用文字。", False)
    return RecognitionResult(text=text, provider="local-whisper", model=model, is_mock=False)


def _recognize_dashscope_image(path: Path, mime: str, attempt_id: str) -> RecognitionResult:
    """Call DashScope Qwen OCR through the OpenAI-compatible vision API."""
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise RecognitionError("provider_not_configured", "未配置 DASHSCOPE_API_KEY。", False)
    model = os.getenv("DASHSCOPE_OCR_MODEL", "qwen3.5-ocr").strip() or "qwen3.5-ocr"
    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    timeout = float(os.getenv("MEDIA_OCR_TIMEOUT_SECONDS", os.getenv("MEDIA_RECOGNITION_TIMEOUT_SECONDS", "60")))
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    data_url = f"data:{mime};base64,{encoded}"
    body = {"model": model, "temperature": 0, "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": data_url}},
        {"type": "text", "text": "请逐字提取图片中的文字。模糊、遮挡或无法确认的字符使用?，不要猜写、补写或解释。只返回识别到的原文。"},
    ]}]}
    req = urllib.request.Request(base_url + "/chat/completions", json.dumps(body, ensure_ascii=False).encode("utf-8"),
        {"Authorization": "Bearer " + api_key, "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        code = "provider_auth_failed" if exc.code in {401, 403} else "provider_rate_limited" if exc.code == 429 else "provider_unavailable"
        raise RecognitionError(code, "云端 OCR 请求失败。", code in {"provider_rate_limited", "provider_unavailable"}) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RecognitionError("provider_timeout" if isinstance(exc, TimeoutError) else "provider_unavailable", "云端 OCR 暂时不可用，可稍后重试。", True) from exc
    try:
        content = payload["choices"][0]["message"]["content"]
        text = content if isinstance(content, str) else "".join(str(x.get("text", "")) for x in content)
    except (KeyError, IndexError, TypeError) as exc:
        raise RecognitionError("invalid_provider_response", "云端 OCR 返回格式无效。", True) from exc
    if not text.strip():
        raise RecognitionError("no_text_detected", "照片中没有识别到可用文字。", False)
    return RecognitionResult(text=text.strip(), provider="dashscope", model=model, is_mock=False)



def _recognize_image(path: Path, mime: str, attempt_id: str) -> RecognitionResult:
    provider = _provider_name("image")
    if provider in {"mock", "test"}:
        raise RecognitionError("mock_provider_not_allowed", "识别模块不在生产调用中自动使用 Mock。", False)
    if provider in {"dashscope", "aliyun", "aliyun-ocr", "qwen-ocr"}:
        return _recognize_dashscope_image(path, mime, attempt_id)
    if provider not in {"local", "vision", "macos-vision"}:
        raise RecognitionError("provider_not_configured", "当前未配置支持的 OCR 服务。", False)
    binary = Path(os.getenv("VISION_OCR_BINARY", str(DEFAULT_VISION_BINARY))).expanduser()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RecognitionError("provider_not_configured", "本机 Vision OCR 适配器未编译。", False)
    timeout = float(os.getenv("MEDIA_OCR_TIMEOUT_SECONDS", os.getenv("MEDIA_RECOGNITION_TIMEOUT_SECONDS", "60")))
    payload = _run_json_command([str(binary), str(path), attempt_id], timeout)
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RecognitionError("no_text_detected", "照片中没有识别到可用文字。", False)
    return RecognitionResult(text=text, provider="macos-vision", model="VNRecognizeTextRequest", is_mock=False)


def recognize_file(path: str | os.PathLike[str], *, kind: str, content_type: str | None = None, attempt_id: str = "") -> dict[str, Any]:
    """Recognize one immutable, already-saved file.

    The function only reads ``path``.  It never creates an Event, writes a
    database row, changes the input file or retries an external provider.
    """
    normalized_kind = _safe_kind(kind)
    file_path, mime = _validate_file(path, normalized_kind, content_type)
    if not str(attempt_id).strip():
        raise RecognitionError("attempt_id_required", "识别尝试编号不能为空。", False)
    if normalized_kind == "audio":
        return _recognize_audio(file_path, mime, str(attempt_id)).as_dict()
    return _recognize_image(file_path, mime, str(attempt_id)).as_dict()


__all__ = ["RecognitionError", "RecognitionResult", "recognize_file"]
