"""统一启动台 - FastAPI 入口"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, HOST, PORT, REPO_ROOT
from .manager import list_status, start_all, start_tool, stop_tool

app = FastAPI(title="统一启动台", docs_url="/api/docs", openapi_url="/api/openapi.json")
WEB_DIR = BASE_DIR / "web"


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/health")
async def health():
    tools = list_status()
    return {
        "ok": True,
        "repo": str(REPO_ROOT),
        "online": sum(1 for t in tools if t["online"]),
        "total": len(tools),
    }


@app.get("/api/tools")
async def api_tools():
    return {"items": list_status()}


@app.post("/api/tools/{tool_id}/start")
async def api_start(tool_id: str):
    try:
        return start_tool(tool_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/tools/{tool_id}/stop")
async def api_stop(tool_id: str):
    try:
        return stop_tool(tool_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/tools/start-all")
async def api_start_all():
    return {"items": start_all()}


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


def run() -> None:
    import uvicorn

    print(f"统一启动台已启动： http://{HOST}:{PORT}")
    print(f"仓库目录：{REPO_ROOT}")
    uvicorn.run("server.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    run()
