"""今日待办与番茄钟统计持久化。"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any

from .config import STORE_FILE

_lock = threading.Lock()

_DEFAULT_SETTINGS = {
    "focus_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "long_break_every": 4,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _today_key() -> str:
    return date.today().isoformat()


def _empty_day() -> dict[str, Any]:
    return {
        "todos": [],
        "focus_completed": 0,
        "focus_minutes_total": 0,
        "break_completed": 0,
    }


def _default_store() -> dict[str, Any]:
    return {"settings": dict(_DEFAULT_SETTINGS), "days": {}}


def _read() -> dict[str, Any]:
    if not STORE_FILE.exists():
        return _default_store()
    try:
        data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_store()
        settings = dict(_DEFAULT_SETTINGS)
        raw_settings = data.get("settings") or {}
        if isinstance(raw_settings, dict):
            for k, v in _DEFAULT_SETTINGS.items():
                if k in raw_settings:
                    try:
                        settings[k] = int(raw_settings[k])
                    except (TypeError, ValueError):
                        settings[k] = v
        days = data.get("days") or {}
        if not isinstance(days, dict):
            days = {}
        return {"settings": settings, "days": days}
    except Exception:  # noqa: BLE001
        return _default_store()


def _write(data: dict[str, Any]) -> None:
    STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STORE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _ensure_day(data: dict[str, Any], day: str | None = None) -> dict[str, Any]:
    key = day or _today_key()
    days = data.setdefault("days", {})
    if key not in days or not isinstance(days[key], dict):
        days[key] = _empty_day()
    day_data = days[key]
    day_data.setdefault("todos", [])
    day_data.setdefault("focus_completed", 0)
    day_data.setdefault("focus_minutes_total", 0)
    day_data.setdefault("break_completed", 0)
    if not isinstance(day_data["todos"], list):
        day_data["todos"] = []
    return day_data


def get_settings() -> dict[str, int]:
    with _lock:
        return dict(_read()["settings"])


def update_settings(**kwargs: Any) -> dict[str, int]:
    with _lock:
        data = _read()
        settings = data["settings"]
        for k, default in _DEFAULT_SETTINGS.items():
            if k not in kwargs or kwargs[k] is None:
                continue
            try:
                val = int(kwargs[k])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"无效设置：{k}") from exc
            if k == "long_break_every":
                val = max(1, min(12, val))
            else:
                val = max(1, min(180, val))
            settings[k] = val
        _write(data)
        return dict(settings)


def get_today() -> dict[str, Any]:
    with _lock:
        data = _read()
        day_key = _today_key()
        day = _ensure_day(data, day_key)
        # 读路径也落盘一次，保证今天条目存在
        _write(data)
        todos = list(day["todos"])
        pending = sum(1 for t in todos if not t.get("done"))
        done = sum(1 for t in todos if t.get("done"))
        return {
            "date": day_key,
            "settings": dict(data["settings"]),
            "todos": todos,
            "stats": {
                "pending": pending,
                "done": done,
                "total": len(todos),
                "focus_completed": int(day.get("focus_completed") or 0),
                "focus_minutes_total": int(day.get("focus_minutes_total") or 0),
                "break_completed": int(day.get("break_completed") or 0),
            },
        }


def add_todo(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("待办内容不能为空")
    if len(text) > 500:
        raise ValueError("待办内容过长（最多 500 字）")

    with _lock:
        data = _read()
        day = _ensure_day(data)
        item = {
            "id": uuid.uuid4().hex[:12],
            "text": text,
            "done": False,
            "created_at": _now_iso(),
            "done_at": None,
            "pomos": 0,
        }
        day["todos"].insert(0, item)
        _write(data)
        return item


def update_todo(
    todo_id: str,
    *,
    text: str | None = None,
    done: bool | None = None,
) -> dict[str, Any] | None:
    with _lock:
        data = _read()
        day = _ensure_day(data)
        for item in day["todos"]:
            if item.get("id") != todo_id:
                continue
            if text is not None:
                new_text = text.strip()
                if not new_text:
                    raise ValueError("待办内容不能为空")
                if len(new_text) > 500:
                    raise ValueError("待办内容过长（最多 500 字）")
                item["text"] = new_text
            if done is not None:
                was = bool(item.get("done"))
                item["done"] = bool(done)
                if item["done"] and not was:
                    item["done_at"] = _now_iso()
                elif not item["done"]:
                    item["done_at"] = None
            _write(data)
            return item
        return None


def delete_todo(todo_id: str) -> bool:
    with _lock:
        data = _read()
        day = _ensure_day(data)
        before = len(day["todos"])
        day["todos"] = [t for t in day["todos"] if t.get("id") != todo_id]
        if len(day["todos"]) == before:
            return False
        _write(data)
        return True


def clear_done() -> int:
    with _lock:
        data = _read()
        day = _ensure_day(data)
        before = len(day["todos"])
        day["todos"] = [t for t in day["todos"] if not t.get("done")]
        removed = before - len(day["todos"])
        _write(data)
        return removed


def complete_pomodoro(
    *,
    mode: str = "focus",
    minutes: int | None = None,
    todo_id: str | None = None,
) -> dict[str, Any]:
    mode = (mode or "focus").strip().lower()
    if mode not in {"focus", "short_break", "long_break"}:
        raise ValueError("mode 必须是 focus / short_break / long_break")

    with _lock:
        data = _read()
        settings = data["settings"]
        day = _ensure_day(data)

        if minutes is None:
            if mode == "focus":
                minutes = int(settings["focus_minutes"])
            elif mode == "short_break":
                minutes = int(settings["short_break_minutes"])
            else:
                minutes = int(settings["long_break_minutes"])
        else:
            minutes = max(1, min(180, int(minutes)))

        if mode == "focus":
            day["focus_completed"] = int(day.get("focus_completed") or 0) + 1
            day["focus_minutes_total"] = int(day.get("focus_minutes_total") or 0) + minutes
            if todo_id:
                for item in day["todos"]:
                    if item.get("id") == todo_id:
                        item["pomos"] = int(item.get("pomos") or 0) + 1
                        break
        else:
            day["break_completed"] = int(day.get("break_completed") or 0) + 1

        _write(data)
        return {
            "date": _today_key(),
            "mode": mode,
            "minutes": minutes,
            "focus_completed": int(day["focus_completed"]),
            "focus_minutes_total": int(day["focus_minutes_total"]),
            "break_completed": int(day["break_completed"]),
        }
