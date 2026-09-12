#!/usr/bin/env python3
"""Small subprocess boundary around the locally installed Whisper package."""
from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) != 5:
        print(json.dumps({"ok": False, "error_code": "invalid_provider_response"}))
        return 2
    audio_path, model_name, language, attempt_id = sys.argv[1:5]
    try:
        import whisper  # type: ignore
    except Exception:
        print(json.dumps({"ok": False, "error_code": "provider_not_configured"}))
        return 3
    try:
        model = whisper.load_model(model_name)
        result = model.transcribe(
            audio_path,
            language=language,
            task="transcribe",
            fp16=False,
            temperature=0,
            verbose=False,
        )
        text = result.get("text") if isinstance(result, dict) else None
        if not isinstance(text, str) or not text.strip():
            print(json.dumps({"ok": False, "error_code": "no_text_detected", "attempt_id": attempt_id}))
            return 4
        print(json.dumps({"ok": True, "text": text.strip(), "attempt_id": attempt_id}, ensure_ascii=False))
        return 0
    except TimeoutError:
        print(json.dumps({"ok": False, "error_code": "provider_timeout", "attempt_id": attempt_id}))
        return 5
    except Exception:
        # Keep provider details out of the public response.  The parent process
        # classifies this as an unavailable provider and exposes only a safe
        # message.
        print(json.dumps({"ok": False, "error_code": "provider_unavailable", "attempt_id": attempt_id}))
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
