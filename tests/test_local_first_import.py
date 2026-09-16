import os
import subprocess
import sys


def test_local_first_import_does_not_create_server_health_database(tmp_path):
    database = tmp_path / "must-not-exist.sqlite3"
    env = {
        **os.environ,
        "APP_MODE": "local_first",
        "DB_PATH": str(database),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", "from backend import server; assert server.STORE is None; assert server.MEDIA_BACKEND is None"],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert not database.exists()
