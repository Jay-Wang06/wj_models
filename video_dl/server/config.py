"""全局配置"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = Path(os.environ.get("VIDEODL_DOWNLOAD_DIR", str(BASE_DIR / "downloads")))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 若项目根目录存在 cookies.txt，则自动使用（Netscape 格式，可用于 B 站 1080P+）
COOKIES_FILE = BASE_DIR / "cookies.txt"

# 运行时临时目录（用于存放用户粘贴的 SESSDATA 生成的 cookie 文件）
RUNTIME_DIR = BASE_DIR / ".runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

HOST = os.environ.get("VIDEODL_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIDEODL_PORT", "8765"))

# 代理（优先 VIDEODL_PROXY，其次标准环境变量）。形如 http://127.0.0.1:7890
PROXY = (
    os.environ.get("VIDEODL_PROXY", "").strip()
    or os.environ.get("HTTPS_PROXY", "").strip()
    or os.environ.get("HTTP_PROXY", "").strip()
    or None
)

# 强制 IPv4：部分 Windows 网络 IPv6 链路异常会导致连接被重置（WinError 10054 / curl 35）
FORCE_IPV4 = os.environ.get("VIDEODL_FORCE_IPV4", "1").lower() not in ("0", "false", "no")


def ffmpeg_path() -> str | None:
    """按优先级查找可用的 ffmpeg 路径：环境变量 > 项目 bin/ > 系统 PATH。"""
    if os.environ.get("FFMPEG_LOCATION"):
        p = Path(os.environ["FFMPEG_LOCATION"])
        if p.exists():
            return str(p)
    local = BASE_DIR / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if local.exists():
        return str(local)
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    """检测 ffmpeg 是否可用（用于合并视频+音轨）。"""
    return ffmpeg_path() is not None


def resolve_cookiefile(sessdata: str | None = None) -> str | None:
    """优先使用用户粘贴的 SESSDATA，其次使用项目根目录 cookies.txt。"""
    if sessdata and sessdata.strip():
        value = sessdata.strip()
        path = RUNTIME_DIR / "cookies_sessdata.txt"
        # 简易校验：SESSDATA 形如 xxxxx%2C... 或以数字开头
        if not value.startswith(("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")) and "%" not in value:
            raise ValueError("SESSDATA 格式看起来不正确，请检查后重试（通常是长串字母数字，含 % 符号）")
        lines = [
            "# Netscape HTTP Cookie File",
            ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\t" + value,
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)
    if COOKIES_FILE.exists():
        return str(COOKIES_FILE)
    return None
