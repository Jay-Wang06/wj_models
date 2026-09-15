"""视频下载站 - FastAPI 入口"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import BASE_DIR, DOWNLOAD_DIR, PORT, HOST, ffmpeg_available
from .extractor import parse_video
from .tasks import cancel_task, create_task, delete_task, get_task, list_tasks

app = FastAPI(title="视频下载助手", docs_url="/api/docs", openapi_url="/api/openapi.json")

WEB_DIR = BASE_DIR / "web"


# ---------- 请求/响应模型 ----------
class ParseRequest(BaseModel):
    url: str = Field(..., description="视频地址")
    sessdata: str | None = Field(None, description="B 站 SESSDATA（可选，用于更高清晰度）")
    proxy: str | None = Field(None, description="代理地址（可选），如 http://127.0.0.1:7890")


class DownloadRequest(BaseModel):
    url: str
    selector: str
    title: str = "未命名视频"
    sessdata: str | None = None
    audio_mp3: bool = False
    merge_ext: str | None = None
    proxy: str | None = None


# ---------- 页面 ----------
@app.get("/", response_class=HTMLResponse)
async def index():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


# ---------- API ----------
@app.get("/api/health")
async def health():
    from .extractor import impersonate_available
    return {
        "ok": True,
        "ytdlp_version": yt_dlp.version.__version__,
        "ffmpeg": ffmpeg_available(),
        "impersonate": impersonate_available(),
        "download_dir": str(DOWNLOAD_DIR),
    }


@app.get("/api/diag")
async def api_diag():
    """网络诊断：测试关键站点连通性，定位是否被网络层拦截。"""
    import socket
    import time

    hosts = [
        ("www.bilibili.com", "B 站主站（解析页面必需）"),
        ("api.bilibili.com", "B 站 API（清晰度数据必需）"),
        ("upos-sz-mirrorcos.bilivideo.com", "B 站视频 CDN（下载必需）"),
        ("s1.hdslb.com", "B 站静态资源"),
        ("www.baidu.com", "外网参考（百度）"),
    ]
    results = []
    for host, note in hosts:
        t0 = time.time()
        try:
            addrs = socket.getaddrinfo(host, 443)
        except Exception as exc:  # noqa: BLE001
            results.append({"host": host, "note": note, "ok": False,
                            "ip": "", "detail": f"DNS 解析失败：{exc}", "ms": 0})
            continue
        ip = addrs[0][4][0] if addrs else ""
        err = ""
        ok = False
        for addr in addrs[:6]:
            ip = addr[4][0]
            s = socket.socket(addr[0], socket.SOCK_STREAM)
            s.settimeout(5)
            try:
                s.connect(addr[4])
                ok = True
                break
            except OSError as exc:
                err = str(exc)
            finally:
                s.close()
        ms = int((time.time() - t0) * 1000)
        results.append({
            "host": host, "note": note, "ok": ok,
            "ip": ip if ok else ip,
            "detail": "" if ok else (err or "连接失败"),
            "ms": ms,
        })
    return {"results": results}


@app.post("/api/parse")
async def api_parse(req: ParseRequest):
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(400, "请输入视频地址")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "请输入以 http:// 或 https:// 开头的完整网址")
    try:
        meta = parse_video(url, req.sessdata, proxy=req.proxy)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "id": meta.id,
        "title": meta.title,
        "webpage_url": meta.webpage_url,
        "thumbnail": meta.thumbnail,
        "uploader": meta.uploader,
        "duration_text": meta.duration_text,
        "view_count": meta.view_count,
        "like_count": meta.like_count,
        "extractor": meta.extractor,
        "extractor_key": meta.extractor_key,
        "options": meta.options,
        "playlists": meta.playlists,
    }


@app.post("/api/download")
async def api_download(req: DownloadRequest):
    task = create_task(
        url=req.url.strip(),
        title=req.title,
        selector=req.selector,
        merge_ext=req.merge_ext,
        sessdata=req.sessdata,
        audio_mp3=req.audio_mp3,
        proxy=req.proxy,
    )
    return {"task_id": task.id}


@app.get("/api/tasks")
async def api_tasks():
    return list_tasks()


@app.get("/api/tasks/{task_id}")
async def api_task(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    from .tasks import task_to_dict
    return task_to_dict(task)


@app.post("/api/tasks/{task_id}/cancel")
async def api_cancel(task_id: str):
    ok = cancel_task(task_id)
    if not ok:
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
async def api_delete(task_id: str):
    ok = delete_task(task_id)
    if not ok:
        raise HTTPException(409, "任务不存在或仍在下载中")
    return {"ok": True}


@app.get("/api/tasks/{task_id}/file")
async def api_file(task_id: str):
    task = get_task(task_id)
    if not task or not task.final_path or not Path(task.final_path).exists():
        raise HTTPException(404, "文件不存在或尚未下载完成")
    path = Path(task.final_path)
    filename = quote(path.name)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Content-Length": str(path.stat().st_size),
        },
    )


@app.post("/api/tasks/{task_id}/open")
async def api_open_folder(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    folder = task.task_dir if task.task_dir.exists() else DOWNLOAD_DIR
    try:
        if os.name == "nt":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(folder)])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"无法打开文件夹：{exc}") from exc
    return {"ok": True, "folder": str(folder)}


# ---------- ffmpeg 安装 ----------
@app.get("/api/ffmpeg/status")
async def api_ffmpeg_status():
    """返回当前 ffmpeg 安装状态、最近一次下载进度。"""
    from .config import ffmpeg_path
    from .ffmpeg_helper import get_state

    state = get_state()
    return {
        "available": ffmpeg_available(),
        "path": ffmpeg_path(),
        "install": state,
    }


@app.post("/api/ffmpeg/install")
async def api_ffmpeg_install():
    """后台启动下载并安装 ffmpeg；返回当前任务状态。"""
    from .ffmpeg_helper import get_state, install_ffmpeg

    started = install_ffmpeg()
    return {"started": started, "state": get_state()}


# ---------- 静态资源 ----------
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


def run():
    import uvicorn

    from .extractor import impersonate_available

    print("=" * 56)
    print("  视频下载助手已启动")
    print(f"  本机访问:  http://{HOST}:{PORT}")
    print(f"  下载目录:  {DOWNLOAD_DIR}")
    print(f"  ffmpeg:    {'可用' if ffmpeg_available() else '未安装（高清合并受限）'}")
    print(f"  指纹伪装:  {'可用（Chrome）' if impersonate_available() else '不可用（安装 curl_cffi 可提升兼容性）'}")
    print("=" * 56)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    run()
