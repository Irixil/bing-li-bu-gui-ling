from __future__ import annotations

import json
import os
import stat
import textwrap
import time
from pathlib import Path

import pytest

from backend.recognition import RecognitionError, recognize_file


def make_file(tmp_path: Path, name: str = "sample.wav", content: bytes = b"RIFF-test") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def make_wav_file(tmp_path: Path, name: str = "sample.wav") -> Path:
    return make_file(tmp_path, name, b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 32)


def make_json_runner(tmp_path: Path, payload: dict, *, sleep: float = 0, exit_code: int = 0) -> Path:
    runner = tmp_path / "runner.py"
    runner.write_text(
        textwrap.dedent(
            f"""
            #!/usr/bin/env python3
            import json, sys, time
            time.sleep({sleep!r})
            payload = {payload!r}
            print(json.dumps(payload, ensure_ascii=False))
            raise SystemExit({exit_code})
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return runner


def configure_audio(monkeypatch: pytest.MonkeyPatch, runner: Path, **extra: str) -> None:
    monkeypatch.setenv("MEDIA_ASR_PROVIDER", "local")
    monkeypatch.setenv("WHISPER_PYTHON", os.environ.get("PYTHON", os.sys.executable))
    monkeypatch.setenv("WHISPER_RUNNER", str(runner))
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def configure_image(monkeypatch: pytest.MonkeyPatch, runner: Path, **extra: str) -> None:
    monkeypatch.setenv("MEDIA_OCR_PROVIDER", "local")
    monkeypatch.setenv("VISION_OCR_BINARY", str(runner))
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def assert_error(call, code: str) -> RecognitionError:
    with pytest.raises(RecognitionError) as raised:
        call()
    assert raised.value.code == code
    assert raised.value.as_dict()["message"]
    return raised.value


def test_audio_result_is_uniform_and_input_is_read_only(tmp_path, monkeypatch):
    path = make_wav_file(tmp_path)
    before = path.read_bytes()
    runner = make_json_runner(tmp_path, {"ok": True, "text": "妈妈今天头晕", "attempt_id": "a1"})
    configure_audio(monkeypatch, runner)

    result = recognize_file(path, kind="audio", content_type="audio/wav", attempt_id="a1")

    assert result == {
        "text": "妈妈今天头晕",
        "provider": "local-whisper",
        "model": "base",
        "is_mock": False,
    }
    assert path.read_bytes() == before


def test_image_result_is_uniform(tmp_path, monkeypatch):
    path = make_file(tmp_path, "sample.png", b"\x89PNG\r\n\x1a\nPNG-test")
    runner = make_json_runner(tmp_path, {"ok": True, "text": "药品：氨氯地平片 5 mg", "attempt_id": "o1"})
    # The helper is a subprocess, so a Python executable is sufficient as a
    # deterministic provider substitute for the module test.
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
    configure_image(monkeypatch, runner)

    result = recognize_file(path, kind="image", content_type="image/png", attempt_id="o1")

    assert result["text"] == "药品：氨氯地平片 5 mg"
    assert result["provider"] == "macos-vision"
    assert result["model"] == "VNRecognizeTextRequest"
    assert result["is_mock"] is False


def test_missing_attempt_and_bad_media_are_stable(tmp_path, monkeypatch):
    path = make_wav_file(tmp_path)
    assert_error(lambda: recognize_file(path, kind="audio", content_type="audio/wav"), "attempt_id_required")
    assert_error(lambda: recognize_file(tmp_path / "missing.wav", kind="audio", attempt_id="x"), "invalid_media")
    assert_error(lambda: recognize_file(path, kind="audio", content_type="text/plain", attempt_id="x"), "unsupported_format")
    assert_error(lambda: recognize_file(path, kind="video", attempt_id="x"), "unsupported_media_kind")
    empty = make_file(tmp_path, "empty.wav", b"")
    assert_error(lambda: recognize_file(empty, kind="audio", content_type="audio/wav", attempt_id="x"), "invalid_media")


def test_mock_is_never_a_silent_fallback(tmp_path, monkeypatch):
    path = make_wav_file(tmp_path)
    monkeypatch.setenv("MEDIA_ASR_PROVIDER", "mock")
    assert_error(lambda: recognize_file(path, kind="audio", content_type="audio/wav", attempt_id="x"), "mock_provider_not_allowed")


@pytest.mark.parametrize(
    ("payload", "code", "retryable"),
    [
        ({"ok": False, "error_code": "provider_auth_failed"}, "provider_auth_failed", False),
        ({"ok": False, "error_code": "rate_limit"}, "provider_unavailable", True),
        ({"ok": True, "text": ""}, "no_text_detected", False),
    ],
)
def test_provider_failures_are_classified_without_raw_output(tmp_path, monkeypatch, payload, code, retryable):
    path = make_wav_file(tmp_path)
    runner = make_json_runner(tmp_path, payload)
    configure_audio(monkeypatch, runner)
    error = assert_error(lambda: recognize_file(path, kind="audio", content_type="audio/wav", attempt_id="x"), code)
    assert error.retryable is retryable
    assert str(payload) not in error.message
    assert str(path) not in error.message


def test_invalid_json_and_nonzero_are_safe(tmp_path, monkeypatch):
    path = make_wav_file(tmp_path)
    invalid = tmp_path / "invalid.py"
    invalid.write_text("print('not json')\n", encoding="utf-8")
    configure_audio(monkeypatch, invalid)
    assert_error(lambda: recognize_file(path, kind="audio", content_type="audio/wav", attempt_id="x"), "invalid_provider_response")

    failed = make_json_runner(tmp_path, {"ok": False, "error_code": "provider_unavailable"}, exit_code=9)
    configure_audio(monkeypatch, failed)
    assert_error(lambda: recognize_file(path, kind="audio", content_type="audio/wav", attempt_id="x"), "provider_unavailable")


def test_timeout_is_retryable(tmp_path, monkeypatch):
    path = make_wav_file(tmp_path)
    runner = make_json_runner(tmp_path, {"ok": True, "text": "不会返回"}, sleep=0.2)
    configure_audio(monkeypatch, runner, MEDIA_ASR_TIMEOUT_SECONDS="0.03")
    error = assert_error(lambda: recognize_file(path, kind="audio", content_type="audio/wav", attempt_id="x"), "provider_timeout")
    assert error.retryable is True
