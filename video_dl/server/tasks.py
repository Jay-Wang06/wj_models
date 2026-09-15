"""下载任务管理（内存态 + 磁盘文件）"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yt_dlp

from .config import DOWNLOAD_DIR, RUNTIME_DIR, ffmpeg_available
from .extractor import build_ydl_opts


class TaskCancelled(Exception):
    pass


@dataclass
class Task:
    id: str
    url: str
    title: str
    selector: str
    status: str = "pending"          # pending / downloading / processing / done / error / cancelled
    progress: float = 0.0
    speed: float = 0.0               # bytes/s
    eta: int | None = None
    current_file: str | None = None
    total_bytes: int = 0
    downloaded_bytes: int = 0
    final_path: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    file_map: dict = field(default_factory=dict)   # filename -> [done, total]
    cancel_requested: bool = False
    sessdata: str | None = None
    cookie_file: str | None = None
    proxy: str | None = None
    merge_ext: str | None = None
    audio_mp3: bool = False

    @property
    def task_dir(self) -> Path:
        return DOWNLOAD_DIR / self.id


_tasks: dict[str, Task] = {}
_lock = threading.Lock()
_workers: set[str] = set()


def list_tasks() -> list[dict]:
    with _lock:
        items = sorted(_tasks.values(), key=lambda t: t.created_at, reverse=True)
        return [task_to_dict(t) for t in items]


def task_to_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "url": t.url,
        "selector": t.selector,
        "status": t.status,
        "progress": round(t.progress, 1),
        "speed": t.speed,
        "eta": t.eta,
        "current_file": t.current_file,
        "total_bytes": t.total_bytes,
        "downloaded_bytes": t.downloaded_bytes,
        "final_path": t.final_path,
        "error": t.error,
        "created_at": t.created_at,
        "finished_at": t.finished_at,
        "can_download": t.status in ("done",) and t.final_path and Path(t.final_path).exists(),
    }


def get_task(task_id: str) -> Task | None:
    with _lock:
        return _tasks.get(task_id)


def create_task(url: str, title: str, selector: str, merge_ext: str | None,
                sessdata: str | None = None, audio_mp3: bool = False,
                proxy: str | None = None) -> Task:
    task = Task(
        id=uuid.uuid4().hex[:12],
        url=url,
        title=title,
        selector=selector,
        merge_ext=merge_ext,
        sessdata=sessdata,
        audio_mp3=audio_mp3,
        proxy=proxy,
    )
    with _lock:
        _tasks[task.id] = task
    threading.Thread(target=_run_download, args=(task.id,), daemon=True).start()
    return task


def cancel_task(task_id: str) -> bool:
    task = get_task(task_id)
    if not task:
        return False
    task.cancel_requested = True
    return True


def delete_task(task_id: str) -> bool:
    task = get_task(task_id)
    if not task:
        return False
    if task.status in ("downloading", "processing", "pending"):
        return False  # 运行中不可删除
    task.cancel_requested = True
    with _lock:
        _tasks.pop(task_id, None)
    import shutil
    shutil.rmtree(task.task_dir, ignore_errors=True)
    return True


def _run_download(task_id: str) -> None:
    task = get_task(task_id)
    if not task:
        return
    with _lock:
        if task_id in _workers:
            return
        _workers.add(task_id)
    try:
        _download(task)
    except TaskCancelled:
        task.status = "cancelled"
    except Exception as exc:  # noqa: BLE001
        task.status = "error"
        task.error = _clean(str(exc))
    finally:
        task.finished_at = time.time()
        with _lock:
            _workers.discard(task_id)


def _download(task: Task) -> None:
    task.task_dir.mkdir(parents=True, exist_ok=True)
    opts = build_ydl_opts(None, {
        "outtmpl": {"default": str(task.task_dir / "%(title).80s.%(ext)s")},
        "format": task.selector,
        "noprogress": True,
        "windowsfilenames": True,
        "overwrites": True,
        "http_chunk_size": 10485760,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [lambda d: _progress_hook(task, d)],
        "continuedl": True,
        "merge_output_format": task.merge_ext,
        "postprocessors": (
            [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            if task.audio_mp3 else []
        ),
        "ffmpeg_location": _ffmpeg_location(),
    }, proxy=task.proxy)
    if task.sessdata:
        # 用户粘贴 SESSDATA 时在解析阶段生成 cookie 文件，这里复用
        from .config import resolve_cookiefile
        try:
            task.cookie_file = resolve_cookiefile(task.sessdata)
            opts["cookiefile"] = task.cookie_file
        except ValueError:
            pass

    task.status = "downloading"
    ydl = yt_dlp.YoutubeDL(opts)
    try:
        ydl.download([task.url])
    finally:
        task.speed = 0.0

    if task.cancel_requested:
        raise TaskCancelled()

    # 找到最终产出文件（合并后/转换后）
    files = [
        p for p in task.task_dir.iterdir()
        if p.is_file()
        and not p.name.endswith((".part", ".ytdl"))
        and ".f" not in p.suffix.lower() + p.name.lower()
    ]
    if not files:
        raise RuntimeError("下载完成但未找到输出文件")
    final = max(files, key=lambda p: p.stat().st_size)
    task.final_path = str(final)
    task.status = "done"
    task.progress = 100.0


def _progress_hook(task: Task, d: dict) -> None:
    if task.cancel_requested:
        raise TaskCancelled()
    status = d.get("status")
    if status == "downloading":
        fn = Path(d.get("filename") or "unknown").name
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        done = d.get("downloaded_bytes") or 0
        if fn not in task.file_map:
            task.file_map[fn] = [0, 0]
        task.file_map[fn][0] = done
        task.file_map[fn][1] = max(total, task.file_map[fn][1])
        task.downloaded_bytes = sum(v[0] for v in task.file_map.values())
        task.total_bytes = sum(v[1] for v in task.file_map.values())
        if task.total_bytes:
            task.progress = min(99.0, task.downloaded_bytes / task.total_bytes * 100)
        task.speed = d.get("speed") or 0
        task.eta = d.get("eta")
        task.current_file = fn
        task.status = "downloading"
    elif status == "finished":
        task.status = "processing"
        task.progress = 99.0
        task.speed = 0.0


def _ffmpeg_location() -> str | None:
    # 统一走 config 检测：环境变量 FFMPEG_LOCATION > 项目 bin/ > 项目根目录/ffmpeg > PATH
    from .config import ffmpeg_path
    p = ffmpeg_path()
    if p:
        return str(Path(p).parent)
    return None


def _clean(msg: str) -> str:
    msg = (msg or "").strip()
    if "ffmpeg" in msg.lower() and not ffmpeg_available():
        return ("需要 ffmpeg 来合并视频和音频。请安装 ffmpeg 并确保其在 PATH 中，"
                "或将 ffmpeg.exe 放到项目根目录的 ffmpeg/ 文件夹内。\n原始错误：\n" + msg)
    if len(msg) > 800:
        msg = msg[:800] + "…"
    return msg
