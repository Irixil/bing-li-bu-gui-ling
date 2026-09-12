"""启动本地 MVP 服务，并读取项目根目录的 .env（不打印密钥）。"""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
env_file = ROOT / '.env'
if env_file.exists():
    for line in env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
os.environ.setdefault('API_PORT', '18768')
os.environ.setdefault('DB_PATH', str(ROOT / 'runtime' / 'records.sqlite3'))
from .server import serve
serve()
