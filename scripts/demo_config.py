"""Local demo configuration checks. Never contact providers or expose values."""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
from pathlib import Path
from typing import MutableMapping


def load_environment(env_file: Path, environ: MutableMapping[str, str] | None = None) -> None:
    """Load literal KEY=value lines; an existing shell value always wins."""
    env = os.environ if environ is None else environ
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        env.setdefault(key, value)


def prepare_demo_environment(
    root: Path, *, offline: bool = False, environ: MutableMapping[str, str] | None = None
) -> MutableMapping[str, str]:
    env = os.environ if environ is None else environ
    load_environment(root / ".env", env)
    defaults = {
        "MEDIA_UPLOAD_MAX_BYTES": "134217728",
        "MEDIA_UPLOAD_PART_MAX_BYTES": "8388608",
        "MEDIA_UPLOAD_MAX_PARTS": "256",
        "API_PORT": "18768",
        "DB_PATH": str(root / "runtime" / "records.sqlite3"),
        "MEDIA_ROOT": str(root / "runtime" / "media"),
    }
    for key, value in defaults.items():
        env.setdefault(key, value)
    # Explicit offline CLI selection also overrides per-kind providers. Keys
    # and URLs are neither erased nor used by a Mock provider.
    if offline:
        for key in ("MODEL_PROVIDER", "MEDIA_RECOGNITION_PROVIDER", "MEDIA_ASR_PROVIDER", "MEDIA_OCR_PROVIDER"):
            env[key] = "mock"
    # No ALLOWED_ORIGIN default: the API serves its own UI on the same origin.
    return env


def check_demo_configuration(
    env: MutableMapping[str, str], *, offline: bool = False
) -> dict[str, list[str]]:
    """Return only fixed messages/field names, never configured values."""
    issues: dict[str, list[str]] = {"文字整理": [], "语音识别（ASR）": [], "照片识字（OCR）": [], "本地服务": []}

    def value(key: str) -> str:
        return env.get(key, "").strip()

    def required(section: str, *fields: str) -> None:
        issues[section].extend("缺少 " + key for key in fields if not value(key))

    if not offline:
        provider = value("MODEL_PROVIDER").lower()
        if not provider:
            required("文字整理", "MODEL_PROVIDER")
        elif provider == "mock":
            issues["文字整理"].append("在线模式不能使用 Mock；离线回归请显式加 --offline")
        elif provider in {"openai_compatible", "openai", "custom"}:
            required("文字整理", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")
        elif provider in {"deepseek", "deepseek-ai"}:
            required("文字整理", "DEEPSEEK_API_KEY")
            if "DEEPSEEK_MODEL" in env:
                required("文字整理", "DEEPSEEK_MODEL")
        elif provider in {"modelscope", "魔搭"}:
            required("文字整理", "MODELSCOPE_MODEL")
            # Match Config.from_env: its alias is used only when the primary
            # key is absent, not when the shell deliberately sets it empty.
            if not value("MODELSCOPE_ACCESS_TOKEN" if "MODELSCOPE_ACCESS_TOKEN" in env else "MODELSCOPE_TOKEN"):
                issues["文字整理"].append("缺少 MODELSCOPE_ACCESS_TOKEN（或 MODELSCOPE_TOKEN）")
        else:
            issues["文字整理"].append("MODEL_PROVIDER 不受当前文字适配器支持")

        for prefix, section in (("MEDIA_ASR", "语音识别（ASR）"), ("MEDIA_OCR", "照片识字（OCR）")):
            provider = (env.get(prefix + "_PROVIDER") or env.get("MEDIA_RECOGNITION_PROVIDER", "")).strip().lower()
            if not provider:
                issues[section].append("缺少 " + prefix + "_PROVIDER（或 MEDIA_RECOGNITION_PROVIDER）")
            elif provider == "mock":
                issues[section].append("在线模式不能使用 Mock；离线回归请显式加 --offline")
            elif provider not in {"openai_compatible", "openai-compatible"} and not (prefix == "MEDIA_ASR" and provider == "dashscope_streaming"):
                issues[section].append(prefix + "_PROVIDER 不受当前识别适配器支持")
            if provider and provider != "mock":
                required(section, prefix + "_URL", prefix + "_MODEL")
                keys = [prefix + "_API_KEY", "MEDIA_RECOGNITION_API_KEY"]
                if prefix == "MEDIA_ASR" and provider == "dashscope_streaming":
                    keys.append("DASHSCOPE_API_KEY")
                # Mirror the adapter's first non-empty raw-value fallback,
                # then reject a selected value containing only whitespace.
                if not next((env[key] for key in keys if env.get(key)), "").strip():
                    issues[section].append("缺少 " + " / ".join(keys))
            if prefix == "MEDIA_ASR" and provider == "dashscope_streaming":
                if value(prefix + "_URL"):
                    from backend.recognition import RecognitionError, _validate_dashscope_url

                    try:
                        _validate_dashscope_url(value(prefix + "_URL"))
                    except RecognitionError:
                        issues[section].append("MEDIA_ASR_URL 必须为受支持的百炼 wss://…/api-ws/v1/inference 地址")
                if importlib.util.find_spec("websockets") is None:
                    issues[section].append("缺少 websockets 依赖，请安装项目 requirements.txt")
                if shutil.which("ffmpeg") is None:
                    issues[section].append("缺少 ffmpeg，浏览器录音转换无法启动")

    for key in ("MEDIA_UPLOAD_MAX_BYTES", "MEDIA_UPLOAD_PART_MAX_BYTES", "MEDIA_UPLOAD_MAX_PARTS"):
        if not value(key).isdigit() or int(value(key)) <= 0:
            issues["本地服务"].append(key + " 必须为正整数")
    if not value("API_PORT").isdigit() or not 1 <= int(value("API_PORT")) <= 65535:
        issues["本地服务"].append("API_PORT 必须为 1–65535 的整数")
    required("本地服务", "DB_PATH", "MEDIA_ROOT")
    return issues
