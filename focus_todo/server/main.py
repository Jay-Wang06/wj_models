"""番茄钟 + 今日待办 - FastAPI 入口"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import BASE_DIR, DATA_DIR, HOST, PORT
from . import store

app = FastAPI(title="番茄钟 · 今日待办", docs_url="/api/docs", openapi_url="/api/openapi.json")
WEB_DIR = BASE_DIR / "web"


class SettingsUpdate(BaseModel):
    focus_minutes: int | None = None
    short_break_minutes: int | None = None
    long_break_minutes: int | None = None
    long_break_every: int | None = None


class TodoCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


class TodoUpdate(BaseModel):
    text: str | None = Field(None, min_length=1, max_length=500)
    done: bool | None = None


class PomoComplete(BaseModel):
    mode: str = "focus"
    minutes: int | None = None
    todo_id: str | None = None


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/health")
async def health():
    today = store.get_today()
    return {
        "ok": True,
        "data_dir": str(DATA_DIR),
        "date": today["date"],
        "pending": today["stats"]["pending"],
        "focus_completed": today["stats"]["focus_completed"],
    }


@app.get("/api/today")
async def api_today():
    return store.get_today()


@app.put("/api/settings")
async def api_settings(req: SettingsUpdate):
    try:
        return store.update_settings(**req.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/todos")
async def api_add_todo(req: TodoCreate):
    try:
        return store.add_todo(req.text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.patch("/api/todos/{todo_id}")
async def api_update_todo(todo_id: str, req: TodoUpdate):
    try:
        item = store.update_todo(
            todo_id,
            text=req.text,
            done=req.done,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not item:
        raise HTTPException(404, "待办不存在")
    return item


@app.delete("/api/todos/{todo_id}")
async def api_delete_todo(todo_id: str):
    if not store.delete_todo(todo_id):
        raise HTTPException(404, "待办不存在")
    return {"ok": True}


@app.post("/api/todos/clear-done")
async def api_clear_done():
    return {"removed": store.clear_done()}


@app.post("/api/pomodoro/complete")
async def api_pomo_complete(req: PomoComplete):
    try:
        return store.complete_pomodoro(
            mode=req.mode,
            minutes=req.minutes,
            todo_id=req.todo_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


def run() -> None:
    import uvicorn

    print(f"番茄钟 · 今日待办已启动： http://{HOST}:{PORT}")
    print(f"数据目录：{DATA_DIR}")
    uvicorn.run("server.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    run()
