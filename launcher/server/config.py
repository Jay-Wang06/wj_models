"""全局配置"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# 仓库根目录（launcher 的上一级）
REPO_ROOT = BASE_DIR.parent

HOST = os.environ.get("LAUNCHER_HOST", "127.0.0.1")
PORT = int(os.environ.get("LAUNCHER_PORT", "8764"))

# 托管的工具列表（相对仓库根目录）
TOOLS = [
    {
        "id": "video_dl",
        "name": "视频下载助手",
        "desc": "粘贴链接 → 选清晰度 → 下载到本地（B 站等）",
        "dir": "video_dl",
        "port": 8765,
        "logo": "视",
        "accent": "#f59e0b",
    },
    {
        "id": "web_clipper",
        "name": "网页剪藏器",
        "desc": "抽取正文 → Markdown / PDF → 本地搜索",
        "dir": "web_clipper",
        "port": 8766,
        "logo": "藏",
        "accent": "#2aa198",
    },
    {
        "id": "snap_ocr",
        "name": "OCR 截图翻译",
        "desc": "粘贴截图 → 识字 → 中英对照",
        "dir": "snap_ocr",
        "port": 8767,
        "logo": "文",
        "accent": "#38bdf8",
    },
    {
        "id": "local_notes",
        "name": "本地笔记",
        "desc": "闪念 · Markdown · 标签 · 全文搜索",
        "dir": "local_notes",
        "port": 8768,
        "logo": "记",
        "accent": "#818cf8",
    },
    {
        "id": "focus_todo",
        "name": "番茄钟 · 今日待办",
        "desc": "专注计时 · 今日清单 · 本地统计",
        "dir": "focus_todo",
        "port": 8769,
        "logo": "钟",
        "accent": "#10b981",
    },
]
