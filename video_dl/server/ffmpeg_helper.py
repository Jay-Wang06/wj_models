"""内嵌 ffmpeg 的下载与安装辅助。

下载 BtbN/FFmpeg-Builds 的 latest 静态构建（约 80 MB，解压出 ffmpeg.exe 等），
放到项目 bin/ 目录下，免去用户单独安装 ffmpeg 的步骤。

网络层采用"断点续传 + 多次重试"策略，应对机房/限速网络常见的 WinError 10054。
"""
from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .config import BASE_DIR

FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)
ZIP_NAME = "ffmpeg-master-latest-win64-gpl.zip"
CHUNK = 256 * 1024
MAX_RETRIES = 12

_lock = threading.Lock()
_state: dict = {
    "running": False,
    "stage": "idle",     # idle / downloading / extracting / done / error
    "progress": 0.0,     # 0~1
    "received": 0,
    "total": 0,
    "error": None,
}


def get_state() -> dict:
    with _lock:
        return dict(_state)


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


def ffmpeg_dir() -> Path:
    return BASE_DIR / "bin"


def _port_open(host: str, port: int, timeout: float = 0.8) -> bool:
    """快速探测本地端口是否监听（用于发现代理软件）。"""
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _detect_proxy() -> str | None:
    """按优先级探测可用的 HTTP 代理：环境变量 > Windows 系统代理 > 常见本地代理端口。

    很多代理软件（Clash 等）只监听本地端口但未打开"系统代理"开关，
    此时直连 GitHub 会被重置，必须显式走代理。
    """
    for name in ("FFMPEG_PROXY", "VIDEODL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        val = os.environ.get(name, "").strip()
        if val:
            return val

    if os.name == "nt":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            )
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
            if enabled and server:
                server = server.strip()
                if "://" not in server:
                    server = "http://" + server
                return server
        except OSError:
            pass

    if os.name == "nt":
        for port in (7897, 7890, 10809, 10808, 1080, 8888):
            if _port_open("127.0.0.1", port):
                return f"http://127.0.0.1:{port}"
    return None


def install_ffmpeg() -> bool:
    """启动后台线程下载并安装 ffmpeg。返回 True 表示已启动。"""
    if get_state()["running"]:
        return False
    _set(running=True, stage="downloading", progress=0.0, received=0, total=0, error=None)
    t = threading.Thread(target=_worker, daemon=True, name="ffmpeg-installer")
    t.start()
    return True


def _opener() -> tuple[urllib.request.OpenerDirector, str | None]:
    """构造 urllib opener；若探测到代理则走代理。返回 (opener, proxy)。"""
    proxy = _detect_proxy()
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        return urllib.request.build_opener(handler), proxy
    return urllib.request.build_opener(), None


def _worker() -> None:
    try:
        target = ffmpeg_dir()
        target.mkdir(parents=True, exist_ok=True)
        tmp = BASE_DIR / "downloads" / ZIP_NAME
        tmp.parent.mkdir(parents=True, exist_ok=True)
        if tmp.exists():
            tmp.unlink()

        opener, proxy = _opener()

        # 取到期望总大小（HEAD，跟随重定向）
        total = _probe_size(FFMPEG_URL, opener)
        _set(total=total)

        # 带重试与断点续传的循环
        attempt = 0
        while True:
            attempt += 1
            already = tmp.stat().st_size if tmp.exists() else 0
            try:
                req = urllib.request.Request(
                    FFMPEG_URL,
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
                )
                if already > 0:
                    req.add_header("Range", f"bytes={already}-")
                with opener.open(req, timeout=120) as resp:
                    if resp.status not in (200, 206):
                        raise RuntimeError(f"HTTP {resp.status}")
                    if total == 0:
                        total = int(resp.headers.get("Content-Length") or 0) + already
                        _set(total=total)
                    mode = "ab" if resp.status == 206 else "wb"
                    with open(tmp, mode) as f:
                        received = already
                        last_report = time.time()
                        while True:
                            data = resp.read(CHUNK)
                            if not data:
                                break
                            f.write(data)
                            received += len(data)
                            now = time.time()
                            if now - last_report > 0.3 or received == total:
                                _set(
                                    received=received,
                                    progress=(received / total) if total else 0.0,
                                )
                                last_report = now
                # 正常下载结束
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
                if attempt >= MAX_RETRIES:
                    via = f"（代理 {proxy}）" if proxy else "（直连）"
                    raise RuntimeError(f"下载失败{via}，已重试 {attempt} 次：{exc}") from exc
                time.sleep(min(2 * attempt, 15))
                continue

        _set(stage="extracting", progress=1.0)
        _extract_ffmpeg(tmp)
        try:
            tmp.unlink()
        except OSError:
            pass

        _set(stage="done", progress=1.0, running=False)
    except Exception as exc:  # noqa: BLE001
        _set(stage="error", error=str(exc), running=False)


def _probe_size(url: str, opener: urllib.request.OpenerDirector) -> int:
    """用 HEAD 探一下总大小；遇到重定向时跟随。"""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=30) as resp:
            return int(resp.headers.get("Content-Length") or 0)
    except Exception:  # noqa: BLE001
        return 0


def _extract_ffmpeg(zip_path: Path) -> None:
    """从 zip 里挑出 ffmpeg.exe / ffprobe.exe 及依赖 dll 到 bin/。"""
    target = ffmpeg_dir()
    target.mkdir(parents=True, exist_ok=True)
    exe_suffix = ".exe" if os.name == "nt" else ""

    wanted_exes = {f"ffmpeg{exe_suffix}", f"ffprobe{exe_suffix}", f"ffplay{exe_suffix}"}

    extracted = {f"ffmpeg{exe_suffix}": False, f"ffprobe{exe_suffix}": False}

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            base = Path(info.filename).name
            if not base:
                continue
            if base in wanted_exes or (os.name == "nt" and base.lower().endswith(".dll")):
                with zf.open(info) as src, open(target / base, "wb") as dst:
                    dst.write(src.read())
                if base in extracted:
                    extracted[base] = True

    missing = [k for k, v in extracted.items() if not v]
    if missing:
        raise RuntimeError(f"下载完成但未找到 {missing}；可能 ffmpeg 包结构变化")