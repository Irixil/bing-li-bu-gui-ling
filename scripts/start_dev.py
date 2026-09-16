"""Start the frontend and backend as two managed local processes."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time

from scripts.start_app import ROOT, prepare_app_environment


def main() -> int:
    env, _generated_secret = prepare_app_environment(ROOT, environ=dict(os.environ))
    env.setdefault("BINGLI_API_BASE_URL", f"http://127.0.0.1:{env['API_PORT']}")
    generated_password = not (
        env.get("APP_OWNER_PASSWORD", "").strip() or env.get("APP_OWNER_PASSWORD_SHA256", "").strip()
    )
    if generated_password:
        env["APP_OWNER_PASSWORD"] = secrets.token_urlsafe(15)

    print(f"请打开前端页面：http://127.0.0.1:{env['FRONTEND_PORT']}/", flush=True)
    print(f"后端 API：http://127.0.0.1:{env['API_PORT']}/（无需手动打开）", flush=True)
    if generated_password:
        print("本次临时网站访问密码：" + env["APP_OWNER_PASSWORD"], flush=True)
        print("该密码只在本次运行内有效，不会写入代码或 .env。", flush=True)

    processes = [
        subprocess.Popen([sys.executable, "-m", "scripts.start_backend"], cwd=ROOT, env=env),
        subprocess.Popen([sys.executable, "-m", "scripts.start_frontend"], cwd=ROOT, env=env),
    ]
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.2)
        return next((process.returncode or 0 for process in processes if process.poll() is not None), 0)
    except KeyboardInterrupt:
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
