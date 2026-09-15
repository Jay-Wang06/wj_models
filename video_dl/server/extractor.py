"""视频信息解析与下载选项构建（基于 yt-dlp）"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yt_dlp

# 清晰度 -> 中文标签
QUALITY_LABELS = {
    2160: "4K 超清",
    1440: "2K 超清",
    1080: "1080P 高清",
    720: "720P 高清",
    480: "480P 清晰",
    360: "360P 流畅",
    240: "240P 极速",
    144: "144P 极速",
}

# 视频编码 -> (展示名, 排序权重, 说明)
CODEC_ORDER = {
    "avc": ("AVC/H.264", 0, "兼容性最好"),
    "hev": ("HEVC/H.265", 1, "体积更小"),
    "av01": ("AV1", 2, "压缩率最高"),
    "vp9": ("VP9", 3, "压缩率较高"),
}


def _codec_family(vcodec: str | None) -> str | None:
    if not vcodec or vcodec == "none":
        return None
    code = vcodec.split(".")[0].lower()
    for key in ("avc", "hev", "av01", "vp9"):
        if code.startswith(key):
            return key
    return None


def _is_video_only(f: dict) -> bool:
    return f.get("vcodec") not in (None, "none") and f.get("acodec") in (None, "none") and bool(f.get("height"))


def _is_progressive(f: dict) -> bool:
    return f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none") and bool(f.get("height"))


def _is_audio_only(f: dict) -> bool:
    return f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")


def _est_size(f: dict, duration: float | None) -> int | None:
    s = f.get("filesize") or f.get("filesize_approx")
    if s:
        return int(s)
    tbr = f.get("tbr") or f.get("vbr") or f.get("abr")
    if tbr and duration:
        return int(tbr * 1000 * duration / 8)
    return None


def _guess_merge_ext(v_ext: str | None, a_ext: str | None) -> str:
    v = (v_ext or "").lower()
    a = (a_ext or "").lower()
    if v in ("mp4", "m4v", "mov") and a in ("m4a", "mp4", "aac", "mp3"):
        return "mp4"
    if v in ("webm",) and a in ("webm", "opus", "ogg"):
        return "webm"
    return "mkv"


def _fmt_seconds(sec: float | None) -> str:
    if not sec:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_bytes(n: int | None) -> str:
    if not n:
        return "未知大小"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return ""


# 模拟浏览器请求头，规避部分站点对非浏览器 UA 的拦截
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.bilibili.com/",
}

_impersonate_checked = False
_impersonate_available: bool | None = None

# 依次尝试的浏览器指纹目标（B 站风控可能对不同指纹采取不同策略）
IMPERSONATE_TARGETS = ("chrome", "edge", "firefox", "safari")


def impersonate_available() -> bool:
    """是否可用浏览器 TLS 指纹伪装（依赖 curl_cffi）。"""
    global _impersonate_checked, _impersonate_available
    if not _impersonate_checked:
        _impersonate_checked = True
        try:
            import curl_cffi  # noqa: F401
            _impersonate_available = True
        except ImportError:
            _impersonate_available = False
    return bool(_impersonate_available)


def available_impersonate_targets() -> list:
    """返回当前 curl_cffi 实际支持的指纹目标；无 curl_cffi 时为空。"""
    if not impersonate_available():
        return []
    from yt_dlp.networking.impersonate import ImpersonateTarget

    # 不同 yt-dlp 版本中 curl_cffi 处理器的模块路径不同，逐一尝试
    handler = None
    for mod_name in ("yt_dlp.networking._curlcffi", "yt_dlp.networking._curl_cffi"):
        try:
            mod = __import__(mod_name, fromlist=["CurlCffiRequestHandler"])
            cls = getattr(mod, "CurlCffiRequestHandler", None)
            if cls is not None:
                handler = cls()
                break
        except Exception:  # noqa: BLE001
            continue

    out = []
    for name in IMPERSONATE_TARGETS:
        try:
            t = ImpersonateTarget.from_str(name)
            if handler is None or handler.is_supported_target(t):
                out.append(t)
        except Exception:  # noqa: BLE001
            continue
    if not out:
        # 过滤失败时兜底：chrome 是所有 curl_cffi 版本的标准目标
        try:
            out.append(ImpersonateTarget.from_str("chrome"))
        except Exception:  # noqa: BLE001
            pass
    return out


def build_ydl_opts(
    cookiefile: str | None = None,
    extra: dict | None = None,
    proxy: str | None = None,
    force_ipv4: bool | None = None,
    impersonate: str | list | bool = "auto",
) -> dict:
    """构造 yt-dlp 选项。

    proxy:     代理地址（如 http://127.0.0.1:7890），None 时取环境配置
    force_ipv4: 强制 IPv4；None 时取环境配置
    impersonate: "auto"=全部可用指纹目标；单目标名；目标对象/列表；False/None=不伪装
    """
    from .config import PROXY as CFG_PROXY, FORCE_IPV4 as CFG_FORCE_IPV4, ffmpeg_path as _ffmpeg_path

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        "headers": dict(DEFAULT_HEADERS),
    }
    proxy = proxy if proxy is not None else CFG_PROXY
    if proxy:
        opts["proxy"] = proxy
    if force_ipv4 is None:
        force_ipv4 = CFG_FORCE_IPV4
    if force_ipv4:
        opts["force_ipv4"] = True

    # 指纹伪装（yt-dlp 初始化只接受单个目标）
    if impersonate == "auto":
        targets = available_impersonate_targets()
    elif isinstance(impersonate, (list, tuple)):
        targets = list(impersonate)
    elif impersonate:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        targets = [ImpersonateTarget.from_str(str(impersonate))]
    else:
        targets = []
    if targets:
        opts["impersonate"] = targets[0]

    if cookiefile:
        opts["cookiefile"] = cookiefile
    if extra:
        opts.update(extra)
    # 兜底：extra 可能把 ffmpeg_location 覆盖为 None，导致 yt-dlp 认为 ffmpeg 未安装
    if not opts.get("ffmpeg_location"):
        ffp = _ffmpeg_path()
        if ffp:
            opts["ffmpeg_location"] = str(Path(ffp).parent)
    return opts


@dataclass
class VideoMeta:
    id: str
    title: str
    webpage_url: str
    thumbnail: str | None
    uploader: str | None
    duration: float | None
    duration_text: str
    view_count: int | None
    like_count: int | None
    extractor: str | None
    extractor_key: str | None
    options: list[dict] = field(default_factory=list)
    playlists: list[dict] = field(default_factory=list)


def _build_options(info: dict) -> list[dict]:
    """根据 yt-dlp 返回的 formats 构建清晰的下载选项。"""
    fmts: list[dict] = info.get("formats") or []
    if not fmts and info.get("url"):
        # 直接文件链接（yt-dlp 泛解析只返回单一格式），包装为单选项
        fmts = [info]
    duration = info.get("duration")
    options: list[dict] = []
    seen_ids: set[str] = set()

    def add_option(key: str, label: str, sub: str, selector: str, size: int | None,
                   ext: str, note: str, merge: bool, tag: str | None = None):
        if key in seen_ids:
            return
        seen_ids.add(key)
        options.append({
            "id": key,
            "label": label,
            "sub": sub,
            "selector": selector,
            "size": size,
            "size_text": _fmt_bytes(size),
            "ext": ext,
            "note": note,
            "merge": merge,
            "tag": tag,
        })

    # 1) 自动最佳
    best_v = None
    best_a = None
    best_ext = "mkv"
    best_size = None
    for f in fmts:
        if _is_video_only(f):
            if best_v is None or (f.get("tbr") or 0) > (best_v.get("tbr") or 0):
                best_v = f
    for f in fmts:
        if _is_audio_only(f):
            if best_a is None or (f.get("tbr") or 0) > (best_a.get("tbr") or 0):
                best_a = f
    if best_v:
        best_ext = _guess_merge_ext(best_v.get("ext"), best_a.get("ext") if best_a else None)
        best_size = (_est_size(best_v, duration) or 0) + (_est_size(best_a, duration) or 0) if best_a else None
        add_option("auto", "最佳画质（自动）", "自动选择当前可用的最高质量",
                   "bestvideo+bestaudio/best", best_size, best_ext,
                   "由系统自动挑选并合并最高清视频与最佳音轨", True, tag="推荐")

    # 2) 按 (分辨率, 帧率, 编码) 分组的清晰度选项
    groups: dict[tuple[int, bool, str], list[dict]] = {}
    for f in fmts:
        if not f.get("height"):
            continue
        h = int(f["height"])
        fps60 = bool(f.get("fps") and f["fps"] > 30)
        fam = _codec_family(f.get("vcodec")) or "?"
        groups.setdefault((h, fps60, fam), []).append(f)

    def group_rank(key: tuple[int, bool, str]) -> tuple:
        h, fps60, fam = key
        codec_w = CODEC_ORDER.get(fam, (fam, 99, ""))[1]
        return (-h, -fps60, codec_w)

    for (h, fps60, fam), flist in sorted(groups.items(), key=lambda kv: group_rank(kv[0])):
        # 该组里选最清晰的视频源，找最匹配的音轨
        v = max(flist, key=lambda f: (f.get("tbr") or 0, f.get("filesize") or 0))
        candidates = [f for f in fmts if _is_audio_only(f)]
        a = max(candidates, key=lambda f: (f.get("tbr") or 0, f.get("filesize") or 0)) if candidates else None

        prog = [f for f in fmts if _is_progressive(f) and int(f["height"]) == h]
        need_merge = True
        if prog and not v:
            # 有同分辨率单文件（音视频合流）
            v = max(prog, key=lambda f: f.get("tbr") or 0)
            need_merge = False

        if v and _is_progressive(v):
            selector = v["format_id"]
            ext = v.get("ext") or "mp4"
            size = _est_size(v, duration)
            need_merge = False
        elif v and a:
            selector = f"{v['format_id']}+{a['format_id']}"
            ext = _guess_merge_ext(v.get("ext"), a.get("ext"))
            size = (_est_size(v, duration) or 0) + (_est_size(a, duration) or 0)
            need_merge = True
        elif v:
            selector = v["format_id"]
            ext = v.get("ext") or "mp4"
            size = _est_size(v, duration)
            need_merge = False
        else:
            continue

        label = QUALITY_LABELS.get(h, f"{h}P")
        sub_parts = []
        if fps60:
            sub_parts.append("60帧")
        fam_name = CODEC_ORDER.get(fam, (fam.upper(), 99, ""))[0]
        sub_parts.append(fam_name)
        note = f"{'需合并' if need_merge else '单文件'} · {ext}"
        if need_merge:
            note += "（建议安装 ffmpeg）"

        add_option(
            key=f"h{h}{'60' if fps60 else ''}_{fam}",
            label=label,
            sub=" / ".join(sub_parts),
            selector=selector,
            size=size,
            ext=ext,
            note=note,
            merge=need_merge,
        )

    # 3) 仅音频
    audio_candidates = [f for f in fmts if _is_audio_only(f)]
    if audio_candidates:
        a = max(audio_candidates, key=lambda f: f.get("tbr") or 0)
        add_option("audio_best", "仅音频（最佳）", a.get("ext") or "m4a",
                   f"bestaudio/best", _est_size(a, duration), a.get("ext") or "m4a",
                   "只下载最佳音质音轨", False)
        add_option("audio_mp3", "仅音频（MP3）", "转换为 MP3 格式",
                   "bestaudio/best", _est_size(a, duration), "mp3",
                   "下载音轨并转换为 MP3", False)

    # 4) 兜底：至少提供一个可下载选项（如直接文件链接）
    if not options and fmts:
        f = max(fmts, key=lambda x: x.get("filesize") or x.get("tbr") or 0)
        add_option("direct", "直接下载（原文件）", f.get("ext") or "mp4",
                   "best", f.get("filesize") or None, f.get("ext") or "mp4",
                   "以下载单个最佳格式文件", False)

    return options


_RETRYABLE_HINTS = (
    "connection was reset", "connection reset", "10054", "10053", "10060",
    "unexpected_eof", "eof occurred", "timed out", "timeout", "recv failure",
    "socket closed", "broken pipe", "remote host",
)


def _is_retryable_error(msg: str) -> bool:
    low = msg.lower()
    return any(k in low for k in _RETRYABLE_HINTS)


def parse_video(
    url: str,
    sessdata: str | None = None,
    proxy: str | None = None,
    force_ipv4: bool | None = None,
) -> VideoMeta:
    """解析视频地址，返回元信息与下载选项。

    连接被重置/超时等瞬时错误时，自动换用下一个浏览器指纹目标重试。
    """
    from .config import resolve_cookiefile

    cookiefile = resolve_cookiefile(sessdata) if sessdata else None
    # 每个指纹目标依次尝试；无 curl_cffi 时也重试 2 次
    batch = available_impersonate_targets() or [None, None]
    info = None
    last_exc: Exception | None = None
    for imp in batch:
        try:
            opts = build_ydl_opts(
                cookiefile, proxy=proxy, force_ipv4=force_ipv4, impersonate=imp
            )
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            break
        except Exception as exc:  # yt-dlp 抛出的各类下载/解析错误
            last_exc = exc
            continue

    if info is None:
        raise ValueError(f"解析失败：{_clean_error(str(last_exc or ''))}")

    # 处理分P / 播放列表
    if info.get("_type") == "playlist" and info.get("entries"):
        entries = [e for e in info["entries"] if e]
        if len(entries) > 1:
            playlist_meta = VideoMeta(
                id=info.get("id") or "playlist",
                title=info.get("title") or "合集",
                webpage_url=info.get("webpage_url") or url,
                thumbnail=info.get("thumbnail"),
                uploader=info.get("uploader"),
                duration=None,
                duration_text=f"{len(entries)} 个视频",
                view_count=info.get("view_count"),
                like_count=None,
                extractor=info.get("extractor"),
                extractor_key=info.get("extractor_key"),
            )
            playlist_meta.playlists = [
                {
                    "id": e.get("id"),
                    "title": e.get("title") or "",
                    "webpage_url": e.get("webpage_url") or url,
                    "duration_text": _fmt_seconds(e.get("duration")),
                    "thumbnail": e.get("thumbnail"),
                }
                for e in entries[:100]
            ]
            return playlist_meta
        info = entries[0]

    meta = VideoMeta(
        id=info.get("id") or "",
        title=info.get("title") or "未命名视频",
        webpage_url=info.get("webpage_url") or url,
        thumbnail=info.get("thumbnail"),
        uploader=info.get("uploader"),
        duration=info.get("duration"),
        duration_text=_fmt_seconds(info.get("duration")),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
        extractor=info.get("extractor"),
        extractor_key=info.get("extractor_key"),
    )
    meta.options = _build_options(info)
    if not meta.options:
        raise ValueError("该视频没有可下载的清晰度选项")
    return meta


def _clean_error(msg: str) -> str:
    msg = (msg or "").strip()
    # 去掉 ANSI 彩色控制符（如 yt-dlp 输出的 \x1b[0;31m）
    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    msg = ansi_re.sub("", msg)
    # 去掉过长的堆栈/重复行
    lines = [ln.strip() for ln in msg.splitlines() if ln.strip()]
    if len(lines) > 6:
        lines = lines[:3] + ["..."] + lines[-2:]
    out = "\n".join(lines)
    if len(out) > 800:
        out = out[:800] + "…"
    # 连接被重置等场景给出排查建议
    low = out.lower()
    if any(k in low for k in ("10054", "connection was reset", "connection reset", "remote host")):
        out += ("\n\n排查建议：\n"
                "1. 已启用 Chrome 指纹伪装，可稍后重试（风控可能为临时触发）\n"
                "2. 在「高级选项」中粘贴 B 站登录后的 SESSDATA 再试（需登录才能访问的页面）\n"
                "3. 若使用了代理/VPN/加速器，尝试关闭或切换节点\n"
                "4. 可运行 python -m yt_dlp -U 确认 yt-dlp 已是最新版")
    return out
