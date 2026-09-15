"""全局配置"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CLIPPER_DATA_DIR", str(BASE_DIR / "data")))
CLIPS_DIR = DATA_DIR / "clips"
INDEX_FILE = DATA_DIR / "index.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

HOST = os.environ.get("CLIPPER_HOST", "127.0.0.1")
PORT = int(os.environ.get("CLIPPER_PORT", "8766"))

PROXY = (
    os.environ.get("CLIPPER_PROXY", "").strip()
    or os.environ.get("HTTPS_PROXY", "").strip()
    or os.environ.get("HTTP_PROXY", "").strip()
    or None
)

# 单篇文章最多下载的图片数（防止过大页面拖垮）
MAX_IMAGES = int(os.environ.get("CLIPPER_MAX_IMAGES", "40"))
# 请求超时（秒）
FETCH_TIMEOUT = float(os.environ.get("CLIPPER_TIMEOUT", "25"))
