"""剪藏条目的持久化与搜索。"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CLIPS_DIR, INDEX_FILE
from .extractor import ExtractedArticle


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


def _clip_dir(clip_id: str) -> Path:
    return CLIPS_DIR / clip_id


def _safe_filename(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .") or "article"
    return name[:80]


def list_clips(query: str | None = None) -> list[dict[str, Any]]:
    items = _read_index()
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    q = (query or "").strip().lower()
    if not q:
        return items

    tokens = [t for t in re.split(r"\s+", q) if t]
    result = []
    for item in items:
        hay = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("url") or ""),
                str(item.get("site") or ""),
                str(item.get("author") or ""),
                str(item.get("excerpt") or ""),
                str(item.get("search_text") or ""),
            ]
        ).lower()
        if all(t in hay for t in tokens):
            result.append(item)
    return result


def get_clip(clip_id: str) -> dict[str, Any] | None:
    items = _read_index()
    for item in items:
        if item.get("id") == clip_id:
            detail = dict(item)
            md_path = _clip_dir(clip_id) / "article.md"
            meta_path = _clip_dir(clip_id) / "meta.json"
            if md_path.exists():
                detail["markdown"] = md_path.read_text(encoding="utf-8")
            if meta_path.exists():
                try:
                    detail["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    detail["meta"] = {}
            return detail
    return None


def save_clip(article: ExtractedArticle, tags: list[str] | None = None) -> dict[str, Any]:
    clip_id = uuid.uuid4().hex[:12]
    folder = _clip_dir(clip_id)
    images_dir = folder / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    for im in article.images:
        (images_dir / im.local_name).write_bytes(im.data)

    # Markdown 文件头
    header_lines = [
        f"# {article.title}",
        "",
        f"> 来源：[{article.site or article.url}]({article.url})",
    ]
    if article.author:
        header_lines.append(f"> 作者：{article.author}")
    if article.date:
        header_lines.append(f"> 日期：{article.date}")
    header_lines.append(f"> 剪藏时间：{_now_iso()}")
    header_lines.append("")
    header_lines.append("---")
    header_lines.append("")

    body = article.markdown.lstrip()
    # 避免重复标题
    if body.startswith(f"# {article.title}"):
        body = body.split("\n", 1)[1].lstrip() if "\n" in body else ""

    md_content = "\n".join(header_lines) + body
    if not md_content.endswith("\n"):
        md_content += "\n"

    (folder / "article.md").write_text(md_content, encoding="utf-8")

    meta = {
        "id": clip_id,
        "title": article.title,
        "url": article.url,
        "site": article.site,
        "author": article.author,
        "date": article.date,
        "excerpt": article.excerpt,
        "tags": tags or [],
        "image_count": len(article.images),
        "created_at": _now_iso(),
        "images": [
            {"name": im.local_name, "url": im.original_url, "content_type": im.content_type}
            for im in article.images
        ],
    }
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 索引里放一份可搜索正文（截断）
    index_item = {
        "id": clip_id,
        "title": article.title,
        "url": article.url,
        "site": article.site,
        "author": article.author,
        "date": article.date,
        "excerpt": article.excerpt,
        "tags": tags or [],
        "image_count": len(article.images),
        "created_at": meta["created_at"],
        "search_text": (article.text or "")[:8000],
        "filename": f"{_safe_filename(article.title)}.md",
    }

    items = _read_index()
    items.insert(0, index_item)
    _write_index(items)
    return index_item


def delete_clip(clip_id: str) -> bool:
    items = _read_index()
    new_items = [x for x in items if x.get("id") != clip_id]
    if len(new_items) == len(items):
        return False
    _write_index(new_items)
    folder = _clip_dir(clip_id)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    return True


def markdown_path(clip_id: str) -> Path | None:
    path = _clip_dir(clip_id) / "article.md"
    return path if path.exists() else None


def images_dir(clip_id: str) -> Path:
    return _clip_dir(clip_id) / "images"
