"""本地 OCR：基于 RapidOCR（ONNX），支持中英文。"""
from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

_engine = None
_engine_lock = threading.Lock()
_engine_error: str | None = None


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: list[list[float]] = field(default_factory=list)


@dataclass
class OcrResult:
    text: str
    lines: list[OcrLine]
    width: int
    height: int
    elapsed_ms: float


def get_engine_status() -> dict[str, Any]:
    return {
        "ready": _engine is not None,
        "error": _engine_error,
    }


def _load_engine():
    global _engine, _engine_error
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        try:
            from rapidocr import RapidOCR

            _engine = RapidOCR()
            _engine_error = None
        except Exception as exc:  # noqa: BLE001
            _engine_error = str(exc)
            raise RuntimeError(f"OCR 引擎初始化失败：{exc}") from exc
        return _engine


def warmup() -> None:
    """启动时预热，避免首次识别过慢。"""
    try:
        _load_engine()
    except Exception:  # noqa: BLE001
        pass


def _bytes_to_rgb(data: bytes) -> tuple[np.ndarray, int, int]:
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise ValueError("无法解析图片，请粘贴或上传 PNG / JPG / WEBP / BMP") from exc

    width, height = img.size
    if width < 2 or height < 2:
        raise ValueError("图片尺寸过小")
    if width * height > 40_000_000:
        raise ValueError("图片过大，请裁剪后再试")

    return np.array(img), width, height


def _parse_output(raw: Any) -> tuple[list[OcrLine], float]:
    """兼容 RapidOCR 3.x Output 对象与旧版 list 结果。"""
    lines: list[OcrLine] = []
    elapsed_s = 0.0

    # RapidOCR 3.x: RapidOCROutput
    if hasattr(raw, "txts"):
        txts = raw.txts or ()
        scores = raw.scores or ()
        boxes = raw.boxes
        elapsed_s = float(getattr(raw, "elapse", 0.0) or 0.0)
        for i, text in enumerate(txts):
            text = str(text or "").strip()
            if not text:
                continue
            score = float(scores[i]) if i < len(scores) else 0.0
            box_list: list[list[float]] = []
            try:
                if boxes is not None and i < len(boxes):
                    box_list = [[float(p[0]), float(p[1])] for p in boxes[i]]
            except Exception:  # noqa: BLE001
                box_list = []
            lines.append(OcrLine(text=text, confidence=score, box=box_list))
        return lines, elapsed_s

    # 旧版: (result_list, elapse)
    if isinstance(raw, tuple) and len(raw) >= 1:
        result_list, elapse = raw[0], raw[1] if len(raw) > 1 else 0
        if isinstance(elapse, (int, float)):
            elapsed_s = float(elapse)
        if result_list:
            for item in result_list:
                if not item or len(item) < 2:
                    continue
                box, text = item[0], str(item[1] or "").strip()
                score = float(item[2]) if len(item) > 2 else 0.0
                if not text:
                    continue
                box_list = []
                try:
                    box_list = [[float(p[0]), float(p[1])] for p in box]
                except Exception:  # noqa: BLE001
                    box_list = []
                lines.append(OcrLine(text=text, confidence=score, box=box_list))
        return lines, elapsed_s

    return lines, elapsed_s


def run_ocr(image_bytes: bytes) -> OcrResult:
    engine = _load_engine()
    image, width, height = _bytes_to_rgb(image_bytes)

    t0 = time.perf_counter()
    raw = engine(image)
    wall_ms = (time.perf_counter() - t0) * 1000

    lines, elapsed_s = _parse_output(raw)
    elapsed_ms = elapsed_s * 1000 if elapsed_s else wall_ms

    def sort_key(line: OcrLine) -> tuple[float, float]:
        if not line.box:
            return (0.0, 0.0)
        ys = [p[1] for p in line.box]
        xs = [p[0] for p in line.box]
        return (sum(ys) / len(ys), sum(xs) / len(xs))

    lines.sort(key=sort_key)
    text = "\n".join(ln.text for ln in lines)

    return OcrResult(
        text=text,
        lines=lines,
        width=width,
        height=height,
        elapsed_ms=round(elapsed_ms, 1),
    )
