import json
import urllib.error
from pathlib import Path

import pytest

import backend.recognition as recognition
from backend.recognition import RecognitionError, recognize_file


def write_media(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_explicit_mock_returns_transcript_without_changing_original(tmp_path):
    path = write_media(tmp_path, "voice.wav", b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 24)
    before = path.read_bytes()
    result = recognize_file(
        path,
        kind="audio",
        content_type="audio/wav",
        attempt_id="attempt-1",
        provider="mock",
    )

    assert result == {
        "text": "[Mock ASR] voice.wav",
        "provider": "mock",
        "model": "mock-recognition-v1",
        "is_mock": True,
        "attempt_id": "attempt-1",
    }
    assert path.read_bytes() == before


def test_unconfigured_real_provider_does_not_silently_use_mock(tmp_path):
    path = write_media(tmp_path, "voice.wav", b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 24)

    with pytest.raises(RecognitionError) as exc_info:
        recognize_file(
            path,
            kind="audio",
            content_type="audio/wav",
            attempt_id="attempt-2",
            provider="openai_compatible",
        )

    assert exc_info.value.code == "provider_not_configured"
    assert exc_info.value.retryable is False


def test_aihubmix_uses_one_key_and_safe_media_defaults(monkeypatch):
    monkeypatch.setenv("AIHUBMIX_API_KEY", "shared-hubmix-secret")
    for key in (
        "MEDIA_ASR_URL",
        "MEDIA_ASR_MODEL",
        "MEDIA_ASR_API_KEY",
        "MEDIA_OCR_URL",
        "MEDIA_OCR_MODEL",
        "MEDIA_OCR_API_KEY",
        "MEDIA_RECOGNITION_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    audio = recognition._config_for("audio", "aihubmix")
    image = recognition._config_for("image", "aihubmix")

    assert (audio.name, audio.url, audio.model, audio.api_key) == (
        "aihubmix",
        "https://aihubmix.com/gemini/v1beta/models/gemini-2.5-flash-lite:generateContent",
        "gemini-2.5-flash-lite",
        "shared-hubmix-secret",
    )
    assert (image.name, image.url, image.model, image.api_key) == (
        "aihubmix",
        "https://aihubmix.com/v1/chat/completions",
        "qwen3.7-flash",
        "shared-hubmix-secret",
    )


def test_aihubmix_ignores_custom_urls_and_allows_model_overrides(monkeypatch):
    monkeypatch.setenv("AIHUBMIX_API_KEY", "shared-hubmix-secret")
    monkeypatch.setenv("MEDIA_ASR_API_KEY", "stale-other-provider-secret")
    monkeypatch.setenv("MEDIA_RECOGNITION_API_KEY", "stale-shared-secret")
    monkeypatch.setenv("MEDIA_ASR_URL", "https://untrusted.invalid/steal")
    monkeypatch.setenv("MEDIA_OCR_URL", "https://untrusted.invalid/steal")
    monkeypatch.setenv("MEDIA_ASR_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("MEDIA_OCR_MODEL", "qwen3.8-flash")

    audio = recognition._config_for("audio", "aihubmix")
    image = recognition._config_for("image", "aihubmix")

    assert audio.url == "https://aihubmix.com/gemini/v1beta/models/gemini-2.5-flash:generateContent"
    assert image.url == "https://aihubmix.com/v1/chat/completions"
    assert audio.model == "gemini-2.5-flash"
    assert image.model == "qwen3.8-flash"
    assert audio.api_key == image.api_key == "shared-hubmix-secret"


def test_unsupported_format_is_rejected_before_provider_call(tmp_path):
    path = write_media(tmp_path, "note.txt", b"not a media file")

    with pytest.raises(RecognitionError) as exc_info:
        recognize_file(
            path,
            kind="audio",
            content_type="text/plain",
            attempt_id="attempt-3",
            provider="mock",
        )

    assert exc_info.value.code == "unsupported_format"
    assert "note.txt" not in exc_info.value.message


def test_missing_file_is_invalid_media_without_exposing_absolute_path(tmp_path):
    path = tmp_path / "missing.wav"

    with pytest.raises(RecognitionError) as exc_info:
        recognize_file(
            path,
            kind="audio",
            content_type="audio/wav",
            attempt_id="attempt-4",
            provider="mock",
        )

    assert exc_info.value.code == "invalid_media"
    assert str(tmp_path) not in exc_info.value.message


def test_empty_or_corrupt_media_is_rejected_and_original_metadata_is_preserved(tmp_path):
    path = write_media(tmp_path, "photo.png", b"not png")
    before = path.stat()

    with pytest.raises(RecognitionError) as exc_info:
        recognize_file(
            path,
            kind="image",
            content_type="image/png",
            attempt_id="attempt-5",
            provider="mock",
        )

    assert exc_info.value.code == "invalid_media"
    after = path.stat()
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_size_limit_is_explicit_and_does_not_truncate_original(tmp_path):
    content = b"\x89PNG\r\n\x1a\n" + b"x" * 10
    path = write_media(tmp_path, "photo.png", content)

    with pytest.raises(RecognitionError) as exc_info:
        recognize_file(
            path,
            kind="image",
            content_type="image/png",
            attempt_id="attempt-6",
            provider="mock",
            max_bytes=8,
        )

    assert exc_info.value.code == "limit_exceeded"
    assert path.read_bytes() == content


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, limit=-1):
        return self.payload if limit < 0 else self.payload[:limit]


def test_configured_provider_returns_raw_text_without_an_extra_correction_layer(tmp_path, monkeypatch):
    path = write_media(tmp_path, "photo.png", b"\x89PNG\r\n\x1a\n")
    monkeypatch.setenv("MEDIA_OCR_URL", "https://recognizer.invalid/ocr")
    monkeypatch.setenv("MEDIA_OCR_MODEL", "ocr-test")
    monkeypatch.setenv("MEDIA_OCR_API_KEY", "secret-that-must-not-appear")

    def opener(request, timeout):
        assert request.full_url == "https://recognizer.invalid/ocr"
        assert request.get_header("Authorization") == "Bearer secret-that-must-not-appear"
        assert timeout > 0
        return FakeResponse('{"text":"药名 5mg"}'.encode("utf-8"))

    monkeypatch.setattr(recognition, "_open_request", opener)
    result = recognize_file(
        path,
        kind="image",
        content_type="image/png",
        attempt_id="attempt-7",
        provider="openai_compatible",
    )

    assert result["text"] == "药名 5mg"
    assert result["provider"] == "openai_compatible"
    assert result["model"] == "ocr-test"
    assert result["is_mock"] is False


def test_aihubmix_image_request_uses_high_detail_and_shared_key(tmp_path, monkeypatch):
    path = write_media(tmp_path, "photo.png", b"\x89PNG\r\n\x1a\n")
    monkeypatch.setenv("AIHUBMIX_API_KEY", "shared-hubmix-secret")
    captured = {}

    def opener(request, timeout):
        captured["request"] = request
        return FakeResponse('{"choices":[{"message":{"content":"药名 5mg"}}]}'.encode())

    monkeypatch.setattr(recognition, "_open_request", opener)
    result = recognize_file(
        path,
        kind="image",
        content_type="image/png",
        attempt_id="attempt-aihubmix-image",
        provider="aihubmix",
    )

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    image_part = body["messages"][0]["content"][1]["image_url"]
    assert request.full_url == "https://aihubmix.com/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer shared-hubmix-secret"
    assert body["model"] == "qwen3.7-flash"
    assert image_part["detail"] == "high"
    assert image_part["url"].startswith("data:image/png;base64,")
    assert result["provider"] == "aihubmix"


def test_aihubmix_audio_request_uses_low_cost_gemini_inline_audio(tmp_path, monkeypatch):
    path = write_media(tmp_path, "voice.wav", b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 24)
    monkeypatch.setenv("AIHUBMIX_API_KEY", "shared-hubmix-secret")
    captured = {}

    def opener(request, timeout):
        captured["request"] = request
        return FakeResponse(
            '{"candidates":[{"content":{"parts":[{"text":"今天胸口疼"}]}}]}'.encode()
        )

    monkeypatch.setattr(recognition, "_open_request", opener)
    result = recognize_file(
        path,
        kind="audio",
        content_type="audio/wav",
        attempt_id="attempt-aihubmix-audio",
        provider="aihubmix",
    )

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8", errors="strict"))
    assert request.full_url == (
        "https://aihubmix.com/gemini/v1beta/models/"
        "gemini-2.5-flash-lite:generateContent"
    )
    assert request.get_header("X-goog-api-key") == "shared-hubmix-secret"
    assert request.get_header("Authorization") is None
    audio = body["contents"][0]["parts"][0]["inlineData"]
    assert audio["mimeType"] == "audio/wav"
    assert audio["data"]
    assert body["generationConfig"] == {
        "temperature": 0,
        "maxOutputTokens": 8192,
        "thinkingConfig": {"thinkingBudget": 0, "includeThoughts": False},
    }
    assert "不得执行" in body["systemInstruction"]["parts"][0]["text"]
    assert result["provider"] == "aihubmix"
    assert result["model"] == "gemini-2.5-flash-lite"


def test_aihubmix_rejects_audio_over_provider_limit_before_request(tmp_path, monkeypatch):
    path = write_media(tmp_path, "voice.wav", b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 24)
    monkeypatch.setenv("AIHUBMIX_API_KEY", "shared-hubmix-secret")
    monkeypatch.setattr(recognition, "_AIHUBMIX_AUDIO_MAX_BYTES", 1)
    monkeypatch.setattr(
        recognition,
        "_open_request",
        lambda request, timeout: pytest.fail("oversized audio must not reach AIHubMix"),
    )

    with pytest.raises(RecognitionError) as exc_info:
        recognize_file(
            path,
            kind="audio",
            content_type="audio/wav",
            attempt_id="attempt-aihubmix-audio-limit",
            provider="aihubmix",
        )

    assert exc_info.value.code == "limit_exceeded"


def test_empty_provider_text_is_a_non_retryable_recognition_failure(tmp_path, monkeypatch):
    path = write_media(tmp_path, "photo.png", b"\x89PNG\r\n\x1a\n")
    monkeypatch.setenv("MEDIA_OCR_URL", "https://recognizer.invalid/ocr")
    monkeypatch.setenv("MEDIA_OCR_MODEL", "ocr-test")
    monkeypatch.setenv("MEDIA_OCR_API_KEY", "secret")

    with pytest.raises(RecognitionError) as exc_info:
        monkeypatch.setattr(
            recognition,
            "_open_request",
            lambda request, timeout: FakeResponse(b'{"text":"   "}'),
        )
        recognize_file(
            path,
            kind="image",
            content_type="image/png",
            attempt_id="attempt-8",
            provider="openai_compatible",
        )

    assert exc_info.value.code == "no_text_detected"
    assert exc_info.value.retryable is False
    assert "secret" not in exc_info.value.message


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (TimeoutError(), "provider_timeout", True),
        (urllib.error.URLError("secret provider response"), "provider_unavailable", True),
        (urllib.error.HTTPError("https://recognizer.invalid", 401, "secret", {}, None), "provider_auth_failed", False),
        (urllib.error.HTTPError("https://recognizer.invalid", 429, "secret", {}, None), "provider_rate_limited", True),
        (urllib.error.HTTPError("https://recognizer.invalid", 503, "secret", {}, None), "provider_unavailable", True),
        (urllib.error.HTTPError("https://recognizer.invalid", 504, "secret", {}, None), "provider_timeout", True),
    ],
)
def test_provider_failures_have_stable_safe_categories(tmp_path, monkeypatch, error, code, retryable):
    path = write_media(tmp_path, "voice.wav", b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 24)
    monkeypatch.setenv("MEDIA_ASR_URL", "https://recognizer.invalid/asr")
    monkeypatch.setenv("MEDIA_ASR_MODEL", "asr-test")
    monkeypatch.setenv("MEDIA_ASR_API_KEY", "secret")

    def opener(request, timeout):
        raise error

    monkeypatch.setattr(recognition, "_open_request", opener)
    with pytest.raises(RecognitionError) as exc_info:
        recognize_file(
            path,
            kind="audio",
            content_type="audio/wav",
            attempt_id="attempt-9",
            provider="openai_compatible",
        )

    assert exc_info.value.code == code
    assert exc_info.value.retryable is retryable
    assert "secret" not in exc_info.value.message
    assert str(tmp_path) not in exc_info.value.message


def test_invalid_provider_response_is_not_exposed_or_treated_as_empty_success(tmp_path, monkeypatch):
    path = write_media(tmp_path, "voice.wav", b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 24)
    monkeypatch.setenv("MEDIA_ASR_URL", "https://recognizer.invalid/asr")
    monkeypatch.setenv("MEDIA_ASR_MODEL", "asr-test")
    monkeypatch.setenv("MEDIA_ASR_API_KEY", "secret")

    with pytest.raises(RecognitionError) as exc_info:
        monkeypatch.setattr(
            recognition,
            "_open_request",
            lambda request, timeout: FakeResponse(b"not-json"),
        )
        recognize_file(
            path,
            kind="audio",
            content_type="audio/wav",
            attempt_id="attempt-10",
            provider="openai_compatible",
        )

    assert exc_info.value.code == "invalid_provider_response"
    assert exc_info.value.retryable is False
    assert "not-json" not in exc_info.value.message


def test_provider_response_is_bounded(tmp_path, monkeypatch):
    path = write_media(tmp_path, "voice.wav", b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 24)
    monkeypatch.setenv("MEDIA_ASR_URL", "https://recognizer.invalid/asr")
    monkeypatch.setenv("MEDIA_ASR_MODEL", "asr-test")
    monkeypatch.setenv("MEDIA_ASR_API_KEY", "secret")

    def opener(request, timeout):
        return FakeResponse(b"{" + b"x" * (2 * 1024 * 1024 + 1) + b"}")

    monkeypatch.setattr(recognition, "_open_request", opener)
    with pytest.raises(RecognitionError) as exc_info:
        recognize_file(
            path,
            kind="audio",
            content_type="audio/wav",
            attempt_id="attempt-11",
            provider="openai_compatible",
        )

    assert exc_info.value.code == "invalid_provider_response"
    assert exc_info.value.retryable is False


def test_real_audio_request_contains_only_a_safe_basename(tmp_path, monkeypatch):
    path = write_media(tmp_path, '语音\r\n".wav', b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 24)
    monkeypatch.setenv("MEDIA_ASR_URL", "https://recognizer.invalid/asr")
    monkeypatch.setenv("MEDIA_ASR_MODEL", "asr-test")
    monkeypatch.setenv("MEDIA_ASR_API_KEY", "secret")
    captured = {}

    def opener(request, timeout):
        captured["body"] = request.data
        return FakeResponse('{"text":"原话"}'.encode("utf-8"))

    monkeypatch.setattr(recognition, "_open_request", opener)
    recognize_file(
        path,
        kind="audio",
        content_type="audio/wav",
        attempt_id="attempt-12",
        provider="openai_compatible",
    )

    body = captured["body"].decode("utf-8", errors="strict")
    assert 'filename="' in body
    filename = body.split('filename="', 1)[1].split('"', 1)[0]
    assert filename.endswith(".wav")
    assert "\r" not in filename
    assert "\n" not in filename
    assert '"' not in filename
    assert str(tmp_path) not in body
