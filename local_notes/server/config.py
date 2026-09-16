"""全局配置"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("NOTES_DATA_DIR", str(BASE_DIR / "data")))
NOTES_DIR = DATA_DIR / "notes"
INDEX_FILE = DATA_DIR / "index.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
NOTES_DIR.mkdir(parents=True, exist_ok=True)

HOST = os.environ.get("NOTES_HOST", "127.0.0.1")
PORT = int(os.environ.get("NOTES_PORT", "8768"))
