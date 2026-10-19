"""检测 / 启动 / 停止各本地小工具。"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import REPO_ROOT, TOOLS


def _tool_by_id(tool_id: str) -> dict | None:
    for t in TOOLS:
        if t["id"] == tool_id:
            return t
    return None


def _tool_dir(tool: dict) -> Path:
    return REPO_ROOT / tool["dir"]


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ok(url: str, timeout: float = 0.8) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def probe_tool(tool: dict) -> dict:
    """返回工具运行时状态。"""
    host = "127.0.0.1"
    port = int(tool["port"])
    path = _tool_dir(tool)
    online = _port_open(host, port)
    healthy = False
    if online:
        healthy = _http_ok(f"http://{host}:{port}/api/health") or _http_ok(
            f"http://{host}:{port}/"
        )

    venv_py = path / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        venv_py = path / ".venv" / "bin" / "python"

    return {
        "id": tool["id"],
        "name": tool["name"],
        "desc": tool["desc"],
        "dir": tool["dir"],
        "path": str(path),
        "exists": path.is_dir(),
        "port": port,
        "url": f"http://{host}:{port}",
        "logo": tool["logo"],
        "accent": tool["accent"],
        "online": online,
        "healthy": healthy,
        "has_venv": venv_py.exists(),
        "has_bat": (path / "启动.bat").exists(),
        "pid": _pid_on_port(port) if online else None,
    }


def list_status() -> list[dict]:
    return [probe_tool(t) for t in TOOLS]


def _pid_on_port(port: int) -> int | None:
    """查找占用端口的 PID（Windows 优先用 netstat）。"""
    if sys.platform == "win32":
        kwargs: dict = {"text": True, "errors": "ignore"}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], **kwargs)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            return None
        suffix = f":{port}"
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            if parts[0].upper() != "TCP":
                continue
            if parts[3].upper() != "LISTENING":
                continue
            if not parts[1].endswith(suffix):
                continue
            try:
                pid = int(parts[-1])
            except ValueError:
                continue
            if pid > 0:
                return pid
        return None

    # Unix: lsof
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            text=True,
            errors="ignore",
        )
        for line in out.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    return None


def _resolve_python(tool_dir: Path) -> str:
    win = tool_dir / ".venv" / "Scripts" / "python.exe"
    unix = tool_dir / ".venv" / "bin" / "python"
    if win.exists():
        return str(win)
    if unix.exists():
        return str(unix)
    return sys.executable


def start_tool(tool_id: str) -> dict:
    tool = _tool_by_id(tool_id)
    if not tool:
        raise ValueError(f"未知工具：{tool_id}")

    path = _tool_dir(tool)
    if not path.is_dir():
        raise FileNotFoundError(f"目录不存在：{path}")

    status = probe_tool(tool)
    if status["online"]:
        return {"ok": True, "already": True, "message": "已在运行", "tool": status}

    bat = path / "启动.bat"
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_CONSOLE

    if bat.exists() and sys.platform == "win32":
        # 用启动.bat：首次会自动建 venv / 装依赖
        subprocess.Popen(
            ["cmd.exe", "/c", "启动.bat"],
            cwd=str(path),
            creationflags=creationflags,
        )
    else:
        py = _resolve_python(path)
        run_py = path / "run.py"
        if not run_py.exists():
            raise FileNotFoundError(f"找不到 run.py：{run_py}")
        subprocess.Popen(
            [py, str(run_py)],
            cwd=str(path),
            creationflags=creationflags,
        )

    # 短暂等待端口起来（最多约 8 秒）
    deadline = time.time() + 8.0
    while time.time() < deadline:
        if _port_open("127.0.0.1", int(tool["port"])):
            break
        time.sleep(0.35)

    status = probe_tool(tool)
    return {
        "ok": True,
        "already": False,
        "message": "已启动" if status["online"] else "已发出启动命令（可能仍在安装依赖）",
        "tool": status,
    }


def stop_tool(tool_id: str) -> dict:
    tool = _tool_by_id(tool_id)
    if not tool:
        raise ValueError(f"未知工具：{tool_id}")

    status = probe_tool(tool)
    if not status["online"]:
        return {"ok": True, "already": True, "message": "未在运行", "tool": status}

    pid = status.get("pid") or _pid_on_port(int(tool["port"]))
    if not pid:
        raise RuntimeError("无法定位占用端口的进程")

    # 不要误杀启动台自己
    if pid == os.getpid():
        raise RuntimeError("拒绝停止启动台自身进程")

    if sys.platform == "win32":
        kill_kwargs: dict = {"check": False, "capture_output": True}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kill_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            **kill_kwargs,
        )
    else:
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass

    deadline = time.time() + 4.0
    while time.time() < deadline:
        if not _port_open("127.0.0.1", int(tool["port"])):
            break
        time.sleep(0.2)

    status = probe_tool(tool)
    return {
        "ok": True,
        "already": False,
        "message": "已停止" if not status["online"] else "已发送停止信号",
        "tool": status,
    }


def start_all() -> list[dict]:
    results = []
    for t in TOOLS:
        try:
            results.append({"id": t["id"], **start_tool(t["id"])})
        except Exception as exc:  # noqa: BLE001
            results.append({"id": t["id"], "ok": False, "message": str(exc)})
    return results
