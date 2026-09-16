"""OCR 截图翻译 - FastAPI 入口"""
from __future__ import annotations

import base64
import binascii
import re
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import BASE_DIR, HOST, MAX_IMAGE_BYTES, PORT
from .ocr import get_engine_status, run_ocr, warmup
from .translate import translate_text

app = FastAPI(title="OCR 截图翻译", docs_url="/api/docs", openapi_url="/api/openapi.json")
WEB_DIR = BASE_DIR / "web"

_DATA_URL_RE = re.compile(r"^data:image/[\w+.-]+;base64,(.+)$", re.I | re.S)


class OcrBase64Request(BaseModel):
    image: str = Field(..., description="图片 base64 或 data URL")
    translate: bool = Field(False, description="识别后是否翻译")
    direction: str = Field("auto", description="auto / zh2en / en2zh")


class TranslateRequest(BaseModel):
    text: str
    direction: str = "auto"


def _decode_image_payload(payload: str) -> bytes:
    raw = (payload or "").strip()
    if not raw:
        raise ValueError("图片内容为空")
    m = _DATA_URL_RE.match(raw)
    if m:
        raw = m.group(1)
    # 去掉空白
    raw = re.sub(r"\s+", "", raw)
    try:
        data = base64.b64decode(raw, validate=False)
    except binascii.Error as exc:
        raise ValueError("图片 base64 解码失败") from exc
    if not data:
        raise ValueError("图片内容为空")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"图片超过大小限制（{MAX_IMAGE_BYTES // (1024 * 1024)}MB）")
    return data


def _ocr_payload(image_bytes: bytes, do_translate: bool, direction: str) -> dict[str, Any]:
    result = run_ocr(image_bytes)
    payload: dict[str, Any] = {
        "text": result.text,
        "line_count": len(result.lines),
        "lines": [
            {"text": ln.text, "confidence": round(ln.confidence, 4)}
            for ln in result.lines
        ],
        "width": result.width,
        "height": result.height,
        "elapsed_ms": result.elapsed_ms,
        "translation": None,
    }
    if do_translate and result.text.strip():
        tr = translate_text(result.text, direction=direction)
        payload["translation"] = {
            "source_lang": tr.source_lang,
            "target_lang": tr.target_lang,
            "translated": tr.translated,
            "bilingual": tr.bilingual,
            "provider": tr.provider,
        }
    return payload


@app.on_event("startup")
async def on_startup() -> None:
    warmup()


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/health")
async def health():
    status = get_engine_status()
    return {
        "ok": True,
        "ocr_ready": status["ready"],
        "ocr_error": status["error"],
        "port": PORT,
    }


@app.post("/api/ocr")
async def api_ocr_upload(
    file: UploadFile = File(...),
    translate: bool = Form(False),
    direction: str = Form("auto"),
):
    data = await file.read()
    if not data:
        raise HTTPException(400, "上传文件为空")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(400, f"图片超过大小限制（{MAX_IMAGE_BYTES // (1024 * 1024)}MB）")
    try:
        return _ocr_payload(data, translate, direction)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"识别失败：{exc}") from exc


@app.post("/api/ocr/base64")
async def api_ocr_base64(req: OcrBase64Request):
    try:
        data = _decode_image_payload(req.image)
        return _ocr_payload(data, req.translate, req.direction)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"识别失败：{exc}") from exc


@app.post("/api/translate")
async def api_translate(req: TranslateRequest):
    try:
        tr = translate_text(req.text, direction=req.direction)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"翻译失败：{exc}") from exc
    return {
        "source_lang": tr.source_lang,
        "target_lang": tr.target_lang,
        "original": tr.original,
        "translated": tr.translated,
        "bilingual": tr.bilingual,
        "provider": tr.provider,
    }


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


def run() -> None:
    import uvicorn

    print(f"OCR 截图翻译已启动： http://{HOST}:{PORT}")
    print("提示：首次识别会加载模型，可能稍慢；翻译需要能访问外网。")
    uvicorn.run("server.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    run()
