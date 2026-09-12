"""识别已保存的音频或图片文件。

这个模块是媒体识别的唯一调用接缝。它不保存文件、不写数据库，也不创建
Event；调用方负责把返回值持久化，并决定何时进行危险扫描和事件关联。

真实供应商通过 OpenAI-compatible 的 HTTP 形状接入，但服务地址、模型和
凭据都必须由调用方显式配置。没有配置时不会退回 Mock。
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


class RecognitionError(RuntimeError):
    """可安全展示给调用方的识别失败。

    ``message`` 不包含供应商原文、密钥或本地绝对路径。A 可以直接把
    ``code``、``message`` 和 ``retryable`` 保存到媒体尝试状态。
    """

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class _Provider(Protocol):
    def recognize(
        self,
        media: bytes,
        *,
        kind: str,
        content_type: str,
        filename: str,
    ) -> str: ...


@dataclass(frozen=True)
class _ProviderConfig:
    name: str
    url: str
    model: str
    api_key: str
    timeout_seconds: float
    max_response_bytes: int


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
_DEFAULT_RESPONSE_BYTES = 2 * 1024 * 1024
_DEFAULT_TIMEOUT_SECONDS = 30.0


def _safe_error(code: str) -> RecognitionError:
    messages = {
        "provider_not_configured": "识别服务未配置",
        "unsupported_format": "不支持的媒体类型或格式",
        "invalid_media": "媒体文件无效或无法读取",
        "limit_exceeded": "媒体超过当前识别服务的资源限制",
        "no_text_detected": "没有识别到可用文字",
        "provider_timeout": "识别服务超时，可稍后重试",
        "provider_unavailable": "识别服务暂时不可用，可稍后重试",
        "provider_auth_failed": "识别服务鉴权失败，请检查配置",
        "provider_rate_limited": "识别服务请求过于频繁，可稍后重试",
        "invalid_provider_response": "识别服务返回了无法使用的结果",
    }
    retryable = code in {
        "provider_timeout",
        "provider_unavailable",
        "provider_rate_limited",
    }
    return RecognitionError(code, messages[code], retryable=retryable)


def _normalise_content_type(content_type: str) -> str:
    if not isinstance(content_type, str):
        raise _safe_error("unsupported_format")
    value = content_type.split(";", 1)[0].strip().lower()
    return value


def _validate_kind_and_type(kind: str, content_type: str) -> tuple[str, str]:
    if kind not in {"audio", "image"}:
        raise _safe_error("unsupported_format")
    normalised = _normalise_content_type(content_type)
    allowed = _AUDIO_TYPES if kind == "audio" else _IMAGE_TYPES
    if normalised not in allowed:
        raise _safe_error("unsupported_format")
    return kind, normalised


def _looks_like_media(data: bytes, content_type: str) -> bool:
    """Perform a small magic-byte check without decoding or rewriting media."""

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


def _read_media(
    path: str | os.PathLike[str],
    *,
    content_type: str,
    max_bytes: int | None,
) -> tuple[Path, bytes]:
    try:
        media_path = Path(path)
        if media_path.is_symlink() or not media_path.is_file():
            raise _safe_error("invalid_media")
        size = media_path.stat().st_size
        if size <= 0:
            raise _safe_error("invalid_media")
        if max_bytes is not None and (max_bytes <= 0 or size > max_bytes):
            raise _safe_error("limit_exceeded")
        data = media_path.read_bytes()
    except RecognitionError:
        raise
    except (OSError, ValueError):
        raise _safe_error("invalid_media") from None
    if len(data) != size or not _looks_like_media(data, content_type):
        raise _safe_error("invalid_media")
    return media_path, data


def _read_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _read_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _config_for(kind: str, provider: str | None) -> _ProviderConfig:
    name = (provider or os.getenv("MEDIA_RECOGNITION_PROVIDER", "")).strip().lower()
    if name in {"", "none", "unconfigured"}:
        raise _safe_error("provider_not_configured")
    if name == "mock":
        return _ProviderConfig(
            name="mock",
            url="",
            model="mock-recognition-v1",
            api_key="",
            timeout_seconds=0,
            max_response_bytes=_DEFAULT_RESPONSE_BYTES,
        )
    if name not in {"openai_compatible", "openai-compatible"}:
        raise _safe_error("provider_not_configured")

    prefix = "MEDIA_ASR" if kind == "audio" else "MEDIA_OCR"
    url = os.getenv(f"{prefix}_URL", "").strip()
    model = os.getenv(f"{prefix}_MODEL", "").strip()
    api_key = os.getenv(f"{prefix}_API_KEY", os.getenv("MEDIA_RECOGNITION_API_KEY", ""))
    if not url or not model or not api_key:
        raise _safe_error("provider_not_configured")
    return _ProviderConfig(
        name="openai_compatible",
        url=url,
        model=model,
        api_key=api_key,
        timeout_seconds=_read_float_env(
            "MEDIA_RECOGNITION_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS
        ),
        max_response_bytes=_read_int_env(
            "MEDIA_RECOGNITION_MAX_RESPONSE_BYTES", _DEFAULT_RESPONSE_BYTES
        ),
    )


class _MockProvider:
    def recognize(
        self,
        media: bytes,
        *,
        kind: str,
        content_type: str,
        filename: str,
    ) -> str:
        del media, content_type
        label = "ASR" if kind == "audio" else "OCR"
        return f"[Mock {label}] {filename}"


class _OpenAICompatibleProvider:
    def __init__(
        self,
        config: _ProviderConfig,
    ) -> None:
        self._config = config

    def recognize(
        self,
        media: bytes,
        *,
        kind: str,
        content_type: str,
        filename: str,
    ) -> str:
        if kind == "audio":
            request = self._audio_request(media, content_type, filename)
        else:
            request = self._image_request(media, content_type, filename)
        return self._send(request)

    def _audio_request(self, media: bytes, content_type: str, filename: str) -> urllib.request.Request:
        boundary = "----bingli-recognition-boundary"
        safe_filename = "".join(
            character if character.isalnum() or character in {".", "-", "_"} else "_"
            for character in Path(filename).name
        )[:120] or "media.bin"
        fields = [
            ("model", self._config.model.encode("utf-8")),
            ("file", media),
        ]
        body = bytearray()
        for name, value in fields:
            body.extend(f"--{boundary}\r\n".encode())
            if name == "file":
                body.extend(
                    (
                        f'Content-Disposition: form-data; name="file"; '
                        f'filename="{safe_filename}"\r\n'
                        f"Content-Type: {content_type}\r\n\r\n"
                    ).encode()
                )
            else:
                body.extend(
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
                )
            body.extend(value)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        return urllib.request.Request(
            self._config.url,
            data=bytes(body),
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

    def _image_request(self, media: bytes, content_type: str, filename: str) -> urllib.request.Request:
        del filename
        image = f"data:{content_type};base64,{base64.b64encode(media).decode('ascii')}"
        body = {
            "model": self._config.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请逐字识别图片中的可见文字。不要补写、纠错或推测；看不清的部分保留为空。",
                        },
                        {"type": "image_url", "image_url": {"url": image}},
                    ],
                }
            ],
        }
        return urllib.request.Request(
            self._config.url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    def _send(self, request: urllib.request.Request) -> str:
        try:
            with urllib.request.urlopen(request, timeout=self._config.timeout_seconds) as response:
                raw = response.read(self._config.max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise _safe_error("provider_auth_failed") from None
            if exc.code == 429:
                raise _safe_error("provider_rate_limited") from None
            if exc.code in {408, 504}:
                raise _safe_error("provider_timeout") from None
            if 500 <= exc.code <= 599:
                raise _safe_error("provider_unavailable") from None
            raise _safe_error("invalid_provider_response") from None
        except TimeoutError:
            raise _safe_error("provider_timeout") from None
        except (urllib.error.URLError, OSError, ValueError):
            raise _safe_error("provider_unavailable") from None
        if len(raw) > self._config.max_response_bytes:
            raise _safe_error("invalid_provider_response")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise _safe_error("invalid_provider_response") from None
        return _text_from_response(payload)


def _text_from_response(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        raise _safe_error("invalid_provider_response")
    if "text" in payload:
        text = payload["text"]
        if not isinstance(text, str):
            raise _safe_error("invalid_provider_response")
    else:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise _safe_error("invalid_provider_response") from None
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            pieces = []
            for item in content:
                if not isinstance(item, Mapping) or not isinstance(item.get("text"), str):
                    raise _safe_error("invalid_provider_response")
                pieces.append(item["text"])
            text = "".join(pieces)
        else:
            raise _safe_error("invalid_provider_response")
    if not text.strip():
        raise _safe_error("no_text_detected")
    return text


def recognize_file(
    path: str | os.PathLike[str],
    *,
    kind: str,
    content_type: str,
    attempt_id: str,
    provider: str | None = None,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    """只读识别文件并返回机器初稿。

    ``provider='mock'`` 只能由调用方显式选择。真实 provider 的配置来自
    ``MEDIA_*`` 环境变量；缺失配置会返回 ``provider_not_configured``。
    ``max_bytes`` 是调用方或已冻结媒体合同提供的大小限制，未提供时不偷偷
    采用产品限制。模块始终对供应商响应设置有界读取。
    """

    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise _safe_error("invalid_media")
    kind, normalised_type = _validate_kind_and_type(kind, content_type)
    media_path, media = _read_media(
        path,
        content_type=normalised_type,
        max_bytes=max_bytes,
    )
    config = _config_for(kind, provider)
    recognizer: _Provider
    if config.name == "mock":
        recognizer = _MockProvider()
    else:
        recognizer = _OpenAICompatibleProvider(config)
    text = recognizer.recognize(
        media,
        kind=kind,
        content_type=normalised_type,
        filename=media_path.name,
    )
    return {
        "text": text,
        "provider": config.name,
        "model": config.model,
        "is_mock": config.name == "mock",
        "attempt_id": attempt_id,
    }
