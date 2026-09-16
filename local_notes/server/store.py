"""笔记持久化、标签与全文搜索。"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import INDEX_FILE, NOTES_DIR

_URL_RE = re.compile(r"^https?://\S+$", re.I)
_TAG_SPLIT = re.compile(r"[,，\s]+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_index() -> list[dict[str, Any]]:
    if not INDEX_FILE.exists():
        return []
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _write_index(items: list[dict[str, Any]]) -> None:
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _note_path(note_id: str) -> Path:
    return NOTES_DIR / f"{note_id}.md"


def normalize_tags(tags: list[str] | str | None) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        parts = _TAG_SPLIT.split(tags)
    else:
        parts = []
        for t in tags:
            parts.extend(_TAG_SPLIT.split(str(t)))
    seen: set[str] = set()
    result: list[str] = []
    for p in parts:
        tag = p.strip().lstrip("#")
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(tag[:40])
    return result[:30]


def _excerpt(text: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _guess_title(body: str, fallback: str = "未命名笔记") -> str:
    for line in (body or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            return s.lstrip("#").strip()[:120] or fallback
        return s[:120]
    return fallback


def is_url(text: str) -> bool:
    t = (text or "").strip()
    return bool(_URL_RE.match(t))


def bookmark_title_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or url
        path = urlparse(url).path or ""
        if path and path not in {"/", ""}:
            leaf = path.rstrip("/").split("/")[-1]
            if leaf:
                return f"{host} / {leaf[:60]}"
        return host
    except Exception:  # noqa: BLE001
        return url[:80]


def list_notes(
    query: str | None = None,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    items = _read_index()
    items.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)

    tag_key = (tag or "").strip().lstrip("#").lower()
    if tag_key:
        items = [
            it
            for it in items
            if tag_key in [str(t).lower() for t in (it.get("tags") or [])]
        ]

    q = (query or "").strip().lower()
    if not q:
        return [{k: v for k, v in it.items() if k != "search_text"} for it in items]

    tokens = [t for t in re.split(r"\s+", q) if t]
    result = []
    for it in items:
        hay = " ".join(
            [
                str(it.get("title") or ""),
                str(it.get("excerpt") or ""),
                " ".join(it.get("tags") or []),
                str(it.get("url") or ""),
                str(it.get("search_text") or ""),
                str(it.get("type") or ""),
            ]
        ).lower()
        if all(tok in hay for tok in tokens):
            result.append({k: v for k, v in it.items() if k != "search_text"})
    return result


def list_tags() -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for it in _read_index():
        for t in it.get("tags") or []:
            key = str(t).lower()
            counts[key] = counts.get(key, 0) + 1
            labels.setdefault(key, str(t))
    rows = [{"tag": labels[k], "count": counts[k]} for k in counts]
    rows.sort(key=lambda x: (-x["count"], x["tag"].lower()))
    return rows


def get_note(note_id: str) -> dict[str, Any] | None:
    items = _read_index()
    for it in items:
        if it.get("id") == note_id:
            detail = {k: v for k, v in it.items() if k != "search_text"}
            path = _note_path(note_id)
            detail["body"] = path.read_text(encoding="utf-8") if path.exists() else ""
            return detail
    return None


def create_note(
    *,
    title: str = "",
    body: str = "",
    tags: list[str] | str | None = None,
    note_type: str = "note",
    url: str | None = None,
) -> dict[str, Any]:
    note_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    body = body or ""
    tags_n = normalize_tags(tags)
    title = (title or "").strip() or _guess_title(body)
    ntype = (note_type or "note").strip().lower()
    if ntype not in {"note", "fleeting", "bookmark"}:
        ntype = "note"

    path = _note_path(note_id)
    path.write_text(body if body.endswith("\n") or not body else body + "\n", encoding="utf-8")

    item = {
        "id": note_id,
        "title": title[:200],
        "tags": tags_n,
        "type": ntype,
        "url": (url or "").strip() or None,
        "excerpt": _excerpt(body),
        "created_at": now,
        "updated_at": now,
        "search_text": body[:12000],
    }
    items = _read_index()
    items.insert(0, item)
    _write_index(items)
    return {k: v for k, v in item.items() if k != "search_text"} | {"body": body}


def update_note(
    note_id: str,
    *,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | str | None = None,
    note_type: str | None = None,
    url: str | None = None,
) -> dict[str, Any] | None:
    items = _read_index()
    idx = next((i for i, it in enumerate(items) if it.get("id") == note_id), None)
    if idx is None:
        return None

    item = dict(items[idx])
    path = _note_path(note_id)
    current_body = path.read_text(encoding="utf-8") if path.exists() else ""

    if body is not None:
        current_body = body
        path.write_text(
            current_body if current_body.endswith("\n") or not current_body else current_body + "\n",
            encoding="utf-8",
        )
        item["excerpt"] = _excerpt(current_body)
        item["search_text"] = current_body[:12000]

    if title is not None:
        item["title"] = (title.strip() or _guess_title(current_body))[:200]
    if tags is not None:
        item["tags"] = normalize_tags(tags)
    if note_type is not None:
        nt = note_type.strip().lower()
        if nt in {"note", "fleeting", "bookmark"}:
            item["type"] = nt
    if url is not None:
        item["url"] = url.strip() or None

    item["updated_at"] = _now_iso()
    items[idx] = item
    _write_index(items)
    out = {k: v for k, v in item.items() if k != "search_text"}
    out["body"] = current_body
    return out


def delete_note(note_id: str) -> bool:
    items = _read_index()
    new_items = [it for it in items if it.get("id") != note_id]
    if len(new_items) == len(items):
        return False
    _write_index(new_items)
    path = _note_path(note_id)
    if path.exists():
        path.unlink()
    return True


def quick_capture(text: str, tags: list[str] | str | None = None) -> dict[str, Any]:
    """粘贴即存：URL → 书签；否则 → 闪念。"""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("内容为空")

    extra_tags = normalize_tags(tags)

    if is_url(raw.split()[0]) and len(raw.split()) == 1:
        url = raw.split()[0]
        title = bookmark_title_from_url(url)
        body = f"# {title}\n\n- 链接：<{url}>\n- 剪藏时间：{_now_iso()}\n"
        return create_note(
            title=title,
            body=body,
            tags=normalize_tags(["书签"] + extra_tags),
            note_type="bookmark",
            url=url,
        )

    # 多行或纯文本 → 闪念
    title = _guess_title(raw, "闪念")
    body = raw if raw.startswith("#") else f"# {title}\n\n{raw}\n"
    return create_note(
        title=title,
        body=body,
        tags=normalize_tags(["闪念"] + extra_tags),
        note_type="fleeting",
    )
