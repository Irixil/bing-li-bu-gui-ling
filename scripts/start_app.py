"""Start the local-first internal beta without storing health records server-side."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path
from typing import MutableMapping

from backend import app_access
from scripts.demo_config import check_demo_configuration, prepare_demo_environment


ROOT = Path(__file__).resolve().parents[1]


def prepare_app_environment(root: Path = ROOT, *, environ: MutableMapping[str, str] | None = None) -> tuple[MutableMapping[str, str], bool]:
    env = prepare_demo_environment(root, environ=os.environ if environ is None else environ)
    env["APP_MODE"] = "local_first"
    env.setdefault("FRONTEND_PORT", "5173")
    env.setdefault("ALLOWED_ORIGIN", f"http://127.0.0.1:{env['FRONTEND_PORT']}")
    generated_session_secret = not bool(env.get("APP_SESSION_SECRET", "").strip())
    if generated_session_secret:
        env["APP_SESSION_SECRET"] = secrets.token_urlsafe(36)
    env.setdefault("APP_COOKIE_SECURE", "false")
    env.setdefault("APP_COOKIE_SAMESITE", "Strict")
    env.setdefault("APP_AI_MEDIA_MAX_BYTES", str(20 * 1024 * 1024))
    return env, generated_session_secret


def main(argv: list[str] | None = None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="病历不归零·内测版：本地加密主数据 + 无状态 AI 接口")
    parser.add_argument("--check-config", action="store_true", help="只检查配置，不启动、不调用 AI")
    args = parser.parse_args(argv)
    try:
        env, generated_secret = prepare_app_environment(root)
    except (OSError, UnicodeError):
        print("无法读取项目 .env，请检查文件权限或 UTF-8 编码。")
        return 2
    issues = check_demo_configuration(env)
    access_configured = app_access.configured()
    print("模式：内测版（健康资料加密保存在浏览器）")
    for section, errors in issues.items():
        print(f"{section}：" + ("；".join(errors) if errors else "配置检查通过"))
    print("网站访问保护：" + ("已配置" if access_configured else "未配置，AI 和云备份功能将拒绝请求"))
    if generated_secret:
        print("本次已生成临时会话签名密钥；正式部署请在平台环境变量中配置 APP_SESSION_SECRET。")
    print("配置检查不会调用外部模型，也不证明真实识别质量。")
    if args.check_config:
        return 0 if access_configured and not any(issues.values()) else 2
    from backend.server import serve

    print(f"后端 API：http://127.0.0.1:{int(env['API_PORT'])}/（不是使用者页面）", flush=True)
    try:
        serve()
    except KeyboardInterrupt:
        print("\n本地服务已停止；浏览器中的加密资料保留。")
    except OSError:
        print("服务启动失败：请检查端口是否被占用。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
