"""Start the local competition demo with safe, explicit offline media settings."""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MODEL_PROVIDER", "mock")
os.environ.setdefault("MEDIA_RECOGNITION_PROVIDER", "mock")
os.environ.setdefault("MEDIA_UPLOAD_MAX_BYTES", "134217728")
os.environ.setdefault("MEDIA_UPLOAD_PART_MAX_BYTES", "8388608")
os.environ.setdefault("MEDIA_UPLOAD_MAX_PARTS", "256")
os.environ.setdefault("API_PORT", "18768")
os.environ.setdefault("DB_PATH", str(ROOT / "runtime" / "records.sqlite3"))
os.environ.setdefault("MEDIA_ROOT", str(ROOT / "runtime" / "media"))
from backend.server import serve
serve()
