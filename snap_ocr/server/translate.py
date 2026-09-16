"""文本翻译：多通道回退（Google → gtx → MyMemory）。"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass
class TranslateResult:
    source_lang: str
    target_lang: str
    original: str
    translated: str
    bilingual: str
    provider: str = ""


def _detect_mainly_chinese(text: str) -> bool:
    if not text.strip():
        return False
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(re.findall(r"[A-Za-z]", text))
    return zh >= en


def resolve_direction(text: str, direction: str) -> tuple[str, str]:
    d = (direction or "auto").strip().lower()
    if d in {"zh2en", "zh-en", "to_en", "en"}:
        return "zh-CN", "en"
    if d in {"en2zh", "en-zh", "to_zh", "zh"}:
        return "en", "zh-CN"
    if _detect_mainly_chinese(text):
        return "zh-CN", "en"
    return "en", "zh-CN"


def _chunk_text(text: str, limit: int) -> list[str]:
    """按行优先切分；单行过长再硬切。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    buf: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal buf, size
        if buf:
            chunks.append("\n".join(buf))
            buf = []
            size = 0

    for line in text.splitlines():
        if len(line) > limit:
            flush()
            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit])
            continue
        add = len(line) + (1 if buf else 0)
        if buf and size + add > limit:
            flush()
        buf.append(line)
        size += add
    flush()
    return chunks


def _short_err(exc: BaseException, limit: int = 180) -> str:
    msg = re.sub(r"\s+", " ", str(exc)).strip()
    # 去掉误返回的整页 HTML
    if "<html" in msg.lower() or "changelog" in msg.lower():
        msg = "接口返回了异常页面（可能被限流或网络拦截）"
    if len(msg) > limit:
        msg = msg[: limit - 1] + "…"
    return msg


def _looks_like_junk(text: str) -> bool:
    low = (text or "").lower()
    if not text.strip():
        return True
    if "<html" in low or "<!doctype" in low:
        return True
    if "changelog" in low and "github" in low:
        return True
    return False


def _http_get_json(url: str, timeout: float = 20.0):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    if _looks_like_junk(raw):
        raise ValueError("接口返回异常内容")
    return json.loads(raw)


def _translate_gtx(chunks: list[str], target: str) -> str:
    """Google 匿名 gtx 接口，通常比 deep-translator 更不易触发 5req/s 限制。"""
    tl = "zh-CN" if target.startswith("zh") else "en"
    parts: list[str] = []
    for i, chunk in enumerate(chunks):
        if i:
            time.sleep(0.15)
        q = urllib.parse.quote(chunk)
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=auto&tl={urllib.parse.quote(tl)}&dt=t&q={q}"
        )
        data = _http_get_json(url)
        # data[0] = [[translated, original, ...], ...]
        segs = []
        if isinstance(data, list) and data and isinstance(data[0], list):
            for item in data[0]:
                if item and isinstance(item, list) and item[0]:
                    segs.append(str(item[0]))
        text = "".join(segs).strip()
        if not text or _looks_like_junk(text):
            raise ValueError("gtx 未返回有效译文")
        parts.append(text)
    return "\n".join(parts).strip()


def _translate_google_lib(chunks: list[str], target: str) -> str:
    from deep_translator import GoogleTranslator

    translator = GoogleTranslator(source="auto", target=target)
    parts: list[str] = []
    for i, chunk in enumerate(chunks):
        if i:
            time.sleep(0.25)
        parts.append(translator.translate(chunk))
    return "\n".join(parts).strip()


def _translate_mymemory(chunks: list[str], source: str, target: str) -> str:
    from deep_translator import MyMemoryTranslator

    def norm(code: str) -> str:
        c = (code or "").lower()
        if c.startswith("zh"):
            return "zh-CN"
        if c.startswith("en"):
            return "en-US"
        return code

    # MyMemory 硬限制约 500 字符
    small_chunks: list[str] = []
    for c in chunks:
        small_chunks.extend(_chunk_text(c, 450))

    translator = MyMemoryTranslator(source=norm(source), target=norm(target))
    parts: list[str] = []
    for i, chunk in enumerate(small_chunks):
        if i:
            time.sleep(0.2)
        out = translator.translate(chunk)
        out = html.unescape(out or "").strip()
        if _looks_like_junk(out):
            raise ValueError("MyMemory 返回异常内容（可能被限流）")
        if "text length need to be between" in out.lower():
            raise ValueError(out)
        parts.append(out)
    return "\n".join(parts).strip()


def translate_text(text: str, direction: str = "auto") -> TranslateResult:
    text = (text or "").strip()
    if not text:
        raise ValueError("没有可翻译的文本")

    source, target = resolve_direction(text, direction)
    # Google/gtx 可用较大块；MyMemory 在各自函数内再切
    chunks = _chunk_text(text, 1800)
    errors: list[str] = []

    providers = [
        ("gtx", lambda: _translate_gtx(chunks, target)),
        ("google", lambda: _translate_google_lib(chunks, target)),
        ("mymemory", lambda: _translate_mymemory(chunks, source, target)),
    ]

    translated = ""
    provider = ""
    for name, fn in providers:
        try:
            translated = fn()
            if not translated.strip():
                raise ValueError("空译文")
            provider = name
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {_short_err(exc)}")

    if not provider:
        raise ValueError(
            "翻译失败（需要可访问外网的翻译接口）。"
            + " 可稍后再试，或先只用识字结果。"
            + (" 详情：" + " | ".join(errors) if errors else "")
        )

    bilingual = _build_bilingual(text, translated)
    return TranslateResult(
        source_lang=source,
        target_lang=target,
        original=text,
        translated=translated,
        bilingual=bilingual,
        provider=provider,
    )


def _build_bilingual(original: str, translated: str) -> str:
    o_lines = original.splitlines()
    t_lines = translated.splitlines()
    if len(o_lines) == len(t_lines) and len(o_lines) > 1:
        blocks = []
        for a, b in zip(o_lines, t_lines):
            if not a.strip() and not b.strip():
                blocks.append("")
            else:
                blocks.append(f"{a}\n{b}")
        return "\n\n".join(blocks).strip() + "\n"
    return f"{original.strip()}\n\n——\n\n{translated.strip()}\n"
