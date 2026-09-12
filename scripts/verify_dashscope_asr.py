"""Run one explicit DashScope ASR smoke test without printing credentials."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.recognition import RecognitionError, recognize_file

DEFAULT_AUDIO = ROOT / "data" / "media_samples" / "fleurs-cmn-validation-1579.wav"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", nargs="?", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--model", default=os.getenv("DASHSCOPE_ASR_MODEL", "qwen3-asr-flash"))
    args = parser.parse_args()
    if not os.getenv("DASHSCOPE_API_KEY", "").strip():
        print(json.dumps({"ok": False, "error": "DASHSCOPE_API_KEY 未配置", "provider": "dashscope"}, ensure_ascii=False))
        return 2
    os.environ["MEDIA_ASR_PROVIDER"] = "dashscope"
    os.environ["DASHSCOPE_ASR_MODEL"] = args.model
    try:
        result = recognize_file(args.audio, kind="audio", content_type="audio/wav", attempt_id="dashscope-smoke-1")
    except RecognitionError as error:
        print(json.dumps({"ok": False, "provider": "dashscope", "error": error.as_dict()}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "provider": result["provider"], "model": result["model"], "text": result["text"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
