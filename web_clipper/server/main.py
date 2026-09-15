"""网页剪藏器 - FastAPI 入口"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import BASE_DIR, CLIPS_DIR, DATA_DIR, HOST, PORT
from .export_pdf import markdown_to_pdf
from .extractor import extract_article
from .store import delete_clip, get_clip, list_clips, markdown_path, save_clip

app = FastAPI(title="网页剪藏器", docs_url="/api/docs", openapi_url="/api/openapi.json")

WEB_DIR = BASE_DIR / "web"


class ClipRequest(BaseModel):
    url: str = Field(..., description="网页地址")
    proxy: str | None = Field(None, description="代理地址（可选）")
    tags: list[str] = Field(default_factory=list)


class PreviewRequest(BaseModel):
    url: str
    proxy: str | None = None


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "data_dir": str(DATA_DIR),
        "clips": len(list_clips()),
    }


@app.post("/api/preview")
async def api_preview(req: PreviewRequest):
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(400, "请输入网页地址")
    try:
        article = extract_article(url, proxy=req.proxy, download_images=False)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "url": article.url,
        "title": article.title,
        "author": article.author,
        "site": article.site,
        "date": article.date,
        "excerpt": article.excerpt,
        "markdown_preview": article.markdown[:4000],
        "text_length": len(article.text or ""),
    }


@app.post("/api/clip")
async def api_clip(req: ClipRequest):
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(400, "请输入网页地址")
    try:
        article = extract_article(url, proxy=req.proxy, download_images=True)
        item = save_clip(article, tags=req.tags)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"剪藏失败：{exc}") from exc
    return item


@app.get("/api/clips")
async def api_list_clips(q: str | None = Query(None, description="搜索关键词")):
    items = list_clips(q)
    # 列表不返回大段 search_text
    slim = []
    for it in items:
        slim.append({k: v for k, v in it.items() if k != "search_text"})
    return {"items": slim, "total": len(slim)}


@app.get("/api/clips/{clip_id}")
async def api_get_clip(clip_id: str):
    item = get_clip(clip_id)
    if not item:
        raise HTTPException(404, "剪藏不存在")
    item.pop("search_text", None)
    return item


@app.delete("/api/clips/{clip_id}")
async def api_delete_clip(clip_id: str):
    if not delete_clip(clip_id):
        raise HTTPException(404, "剪藏不存在")
    return {"ok": True}


@app.get("/api/clips/{clip_id}/markdown")
async def api_download_markdown(clip_id: str):
    item = get_clip(clip_id)
    path = markdown_path(clip_id)
    if not item or not path:
        raise HTTPException(404, "剪藏不存在")
    filename = item.get("filename") or f"{clip_id}.md"
    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.get("/api/clips/{clip_id}/pdf")
async def api_download_pdf(clip_id: str):
    item = get_clip(clip_id)
    md = markdown_path(clip_id)
    if not item or not md:
        raise HTTPException(404, "剪藏不存在")

    folder = CLIPS_DIR / clip_id
    pdf_path = folder / "article.pdf"
    try:
        markdown_to_pdf(md, pdf_path, images_dir=folder / "images")
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"PDF 导出失败：{exc}") from exc

    filename = (item.get("filename") or f"{clip_id}.md").rsplit(".", 1)[0] + ".pdf"
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.get("/api/clips/{clip_id}/images/{name}")
async def api_clip_image(clip_id: str, name: str):
    # 防止路径穿越
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(400, "非法文件名")
    path = CLIPS_DIR / clip_id / "images" / name
    if not path.exists():
        raise HTTPException(404, "图片不存在")
    return FileResponse(path)


@app.get("/api/clips/{clip_id}/content")
async def api_clip_content(clip_id: str):
    """返回可在页面渲染的 Markdown（图片路径改写为 API）。"""
    item = get_clip(clip_id)
    if not item:
        raise HTTPException(404, "剪藏不存在")
    md = item.get("markdown") or ""
    # images/xxx → /api/clips/{id}/images/xxx
    import re

    md = re.sub(
        r"!\[([^\]]*)\]\(images/([^)]+)\)",
        rf"![\1](/api/clips/{clip_id}/images/\2)",
        md,
    )
    return {
        "id": clip_id,
        "title": item.get("title"),
        "url": item.get("url"),
        "markdown": md,
        "created_at": item.get("created_at"),
        "site": item.get("site"),
        "author": item.get("author"),
    }


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


def run() -> None:
    import uvicorn

    print(f"网页剪藏器已启动： http://{HOST}:{PORT}")
    print(f"数据目录：{DATA_DIR}")
    uvicorn.run("server.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    run()
