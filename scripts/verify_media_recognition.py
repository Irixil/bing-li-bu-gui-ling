#!/usr/bin/env python3
"""Run the local ASR/OCR smoke checks and write a redacted evidence record.

This script never contacts a cloud service.  It is intentionally separate from
the API demo: task A owns upload, persistence, retry and Event association.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.recognition import RecognitionError, recognize_file


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return "".join(ch for ch in value if not unicodedata.category(ch).startswith("P") and not ch.isspace())


def run_one(path: Path, *, kind: str, content_type: str, attempt_id: str, expected: str | None = None) -> dict:
    started = time.perf_counter()
    try:
        result = recognize_file(path, kind=kind, content_type=content_type, attempt_id=attempt_id)
        elapsed = round(time.perf_counter() - started, 3)
        row = {
            "ok": True,
            "kind": kind,
            "sample": path.name,
            "elapsed_seconds": elapsed,
            "result": result,
        }
        if expected is not None:
            row["expected_text"] = expected
            row["normalized_exact_match"] = normalized(result["text"]) == normalized(expected)
        return row
    except RecognitionError as exc:
        return {
            "ok": False,
            "kind": kind,
            "sample": path.name,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error": exc.as_dict(),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, default=ROOT / "data/media_samples/fleurs-cmn-validation-1579.wav")
    parser.add_argument("--image", type=Path, default=ROOT / "data/media_samples/合成印刷资料-OCR.png")
    parser.add_argument("--out", type=Path, default=ROOT / "runtime/media-recognition-result.json")
    args = parser.parse_args()

    metadata = json.loads((ROOT / "data/media_samples/fleurs-cmn-validation-1579.json").read_text(encoding="utf-8"))
    expected_ocr = (ROOT / "data/media_samples/合成印刷资料-OCR.txt").read_text(encoding="utf-8").strip()
    rows = [
        run_one(
            args.audio,
            kind="audio",
            content_type="audio/wav",
            attempt_id="verify-asr-1579",
            expected=metadata["raw_transcription"],
        ),
        run_one(
            args.image,
            kind="image",
            content_type="image/png",
            attempt_id="verify-ocr-synthetic-1",
            expected=expected_ocr,
        ),
    ]
    whisper_python = os.environ.get("WHISPER_PYTHON", sys.executable)
    try:
        whisper_version = subprocess.run(
            [whisper_python, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except Exception:
        whisper_version = "unknown"
    evidence = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "platform": "macOS",
            "python": __import__("sys").version.split()[0],
            "asr_python_version": whisper_version,
            "asr_provider": "local-whisper",
            "asr_model": __import__("os").environ.get("WHISPER_MODEL", "base"),
            "ocr_provider": "macos-vision",
            "ocr_model": "VNRecognizeTextRequest",
            "network_upload": False,
        },
        "samples": rows,
        "interpretation": [
            "成功只表示本机识别引擎返回了非空文字。",
            "ASR 与公开原文不完全一致；繁简、标点和字词差异必须由人工核对，不能自动改写药名、数值、单位或日期。",
            "OCR 样例是本项目生成的合成印刷资料，不是医院原始病历。",
            "该脚本不创建 Event、不写数据库、不代表上传、重试、危险扫描或前端链路已经接通。",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "rows": rows}, ensure_ascii=False))
    return 0 if all(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
