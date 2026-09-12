"""启动本地 MVP 服务，并读取项目根目录的 .env（不打印密钥）。"""
from pathlib import Path
import os
from scripts.demo_config import load_environment

ROOT = Path(__file__).resolve().parents[1]
load_environment(ROOT / '.env')
os.environ.setdefault('API_PORT', '18768')
os.environ.setdefault('DB_PATH', str(ROOT / 'runtime' / 'records.sqlite3'))
from .server import serve
if __name__ == '__main__':
    serve()
