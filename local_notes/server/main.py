"""本地笔记 / 闪念 - FastAPI 入口"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import BASE_DIR, DATA_DIR, HOST, PORT
from .store import (
    create_note,
    delete_note,
    get_note,
    list_notes,
    list_tags,
    quick_capture,
    update_note,
)

app = FastAPI(title="本地笔记", docs_url="/api/docs", openapi_url="/api/openapi.json")
WEB_DIR = BASE_DIR / "web"


class NoteCreate(BaseModel):
    title: str = ""
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    type: str = "note"
    url: str | None = None


class NoteUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None
    type: str | None = None
    url: str | None = None


class CaptureRequest(BaseModel):
    text: str = Field(..., description="粘贴的文本或 URL")
    tags: list[str] = Field(default_factory=list)


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "data_dir": str(DATA_DIR),
        "notes": len(list_notes()),
    }


@app.get("/api/notes")
async def api_list_notes(
    q: str | None = Query(None, description="全文搜索"),
    tag: str | None = Query(None, description="按标签筛选"),
):
    items = list_notes(query=q, tag=tag)
    return {"items": items, "total": len(items)}


@app.get("/api/tags")
async def api_tags():
    return {"items": list_tags()}


@app.get("/api/notes/{note_id}")
async def api_get_note(note_id: str):
    note = get_note(note_id)
    if not note:
        raise HTTPException(404, "笔记不存在")
    return note


@app.post("/api/notes")
async def api_create_note(req: NoteCreate):
    return create_note(
        title=req.title,
        body=req.body,
        tags=req.tags,
        note_type=req.type,
        url=req.url,
    )


@app.put("/api/notes/{note_id}")
async def api_update_note(note_id: str, req: NoteUpdate):
    note = update_note(
        note_id,
        title=req.title,
        body=req.body,
        tags=req.tags,
        note_type=req.type,
        url=req.url,
    )
    if not note:
        raise HTTPException(404, "笔记不存在")
    return note


@app.delete("/api/notes/{note_id}")
async def api_delete_note(note_id: str):
    if not delete_note(note_id):
        raise HTTPException(404, "笔记不存在")
    return {"ok": True}


@app.post("/api/capture")
async def api_capture(req: CaptureRequest):
    try:
        return quick_capture(req.text, tags=req.tags)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


def run() -> None:
    import uvicorn

    print(f"本地笔记已启动： http://{HOST}:{PORT}")
    print(f"数据目录：{DATA_DIR}")
    uvicorn.run("server.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    run()
