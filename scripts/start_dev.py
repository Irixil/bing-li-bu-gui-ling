"""Start the frontend and backend as two managed local processes."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from scripts.start_app import ROOT, prepare_app_environment


def main() -> int:
    env, _generated_secret = prepare_app_environment(ROOT, environ=dict(os.environ))
    env.setdefault("BINGLI_API_BASE_URL", f"http://127.0.0.1:{env['API_PORT']}")
    print(f"请打开前端页面：http://127.0.0.1:{env['FRONTEND_PORT']}/", flush=True)
    print(f"后端 API：http://127.0.0.1:{env['API_PORT']}/（无需手动打开）", flush=True)
    print("保存录音或照片后会直接识别；使用者只需本机恢复口令。", flush=True)

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
