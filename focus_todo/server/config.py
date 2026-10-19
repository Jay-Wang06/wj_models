"""全局配置"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("FOCUS_DATA_DIR", str(BASE_DIR / "data")))
STORE_FILE = DATA_DIR / "store.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)

HOST = os.environ.get("FOCUS_HOST", "127.0.0.1")
PORT = int(os.environ.get("FOCUS_PORT", "8769"))
