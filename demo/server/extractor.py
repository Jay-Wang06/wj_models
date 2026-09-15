"""从 URL 抓取网页并抽取正文 + 图片。"""
from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from trafilatura.settings import use_config

from .config import FETCH_TIMEOUT, MAX_IMAGES, PROXY

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

_TRAFILATURA_CFG = use_config()
_TRAFILATURA_CFG.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")


@dataclass
class ExtractedImage:
    original_url: str
    local_name: str
    content_type: str = ""
    data: bytes = b""


@dataclass
class ExtractedArticle:
    url: str
    title: str
    author: str = ""
    site: str = ""
    date: str = ""
    excerpt: str = ""
    markdown: str = ""
    text: str = ""
    images: list[ExtractedImage] = field(default_factory=list)
    html: str = ""


def _client(proxy: str | None = None) -> httpx.Client:
    proxies = proxy or PROXY
    kwargs: dict = {
        "follow_redirects": True,
        "timeout": FETCH_TIMEOUT,
        "headers": {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    }
    if proxies:
        kwargs["proxy"] = proxies
    return httpx.Client(**kwargs)


def _hostname(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001
        return ""


def _clean_title(title: str, site: str) -> str:
    title = (title or "").strip() or "未命名文章"
    # 去掉常见站点后缀
    for sep in (" | ", " - ", " — ", " · ", "_"):
        if site and sep in title:
            parts = title.split(sep)
            if len(parts) >= 2 and site.lower() in parts[-1].lower():
                title = sep.join(parts[:-1]).strip()
    return title[:200]


def _excerpt_from_text(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _ext_from_content_type(ct: str, url: str) -> str:
    ct = (ct or "").split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "image/bmp": ".bmp",
    }
    if ct in mapping:
        return mapping[ct]
    guess = mimetypes.guess_extension(ct or "") or ""
    if guess:
        return ".jpg" if guess == ".jpe" else guess
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def _is_probably_image_url(url: str) -> bool:
    if not url or url.startswith(("data:", "blob:", "javascript:")):
        return False
    low = url.lower()
    if any(x in low for x in ("avatar", "icon", "logo", "sprite", "emoji", "1x1", "pixel")):
        # 仍允许，但后面会按尺寸/体积过滤；这里先不过滤太狠
        pass
    return True


def _collect_image_urls(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html or "", "lxml")
    urls: list[str] = []
    seen: set[str] = set()

    def add(u: str | None) -> None:
        if not u:
            return
        u = unescape(u.strip())
        if u.startswith("//"):
            u = "https:" + u
        abs_u = urljoin(base_url, u)
        if not _is_probably_image_url(abs_u):
            return
        if abs_u in seen:
            return
        seen.add(abs_u)
        urls.append(abs_u)

    for img in soup.find_all("img"):
        # 优先大图属性
        for attr in ("data-src", "data-original", "data-lazy-src", "src"):
            val = img.get(attr)
            if val:
                add(val)
                break
        srcset = img.get("srcset") or img.get("data-srcset")
        if srcset:
            # 取 srcset 里最大的一张
            parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
            if parts:
                add(parts[-1])

    return urls[: MAX_IMAGES * 2]  # 多取一些，下载失败再筛


def _download_images(
    urls: list[str],
    client: httpx.Client,
    referer: str,
) -> list[ExtractedImage]:
    images: list[ExtractedImage] = []
    for i, url in enumerate(urls, start=1):
        if len(images) >= MAX_IMAGES:
            break
        try:
            resp = client.get(url, headers={"Referer": referer})
            if resp.status_code >= 400:
                continue
            ct = resp.headers.get("content-type", "")
            if "image" not in ct.lower() and not urlparse(url).path.lower().endswith(
                (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg")
            ):
                continue
            data = resp.content
            if len(data) < 800:  # 跳过极小图（追踪像素等）
                continue
            if len(data) > 8 * 1024 * 1024:  # 单图上限 8MB
                continue
            ext = _ext_from_content_type(ct, url)
            digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
            local_name = f"{i:03d}_{digest}{ext}"
            images.append(
                ExtractedImage(
                    original_url=url,
                    local_name=local_name,
                    content_type=ct.split(";")[0].strip(),
                    data=data,
                )
            )
        except Exception:  # noqa: BLE001
            continue
    return images


def _html_to_markdown_with_images(
    html: str,
    base_url: str,
    url_to_local: dict[str, str],
) -> str:
    """简易 HTML → Markdown，并把图片替换为本地相对路径。"""
    soup = BeautifulSoup(html or "", "lxml")

    # 去掉脚本样式
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    lines: list[str] = []

    def walk(node, list_prefix: str = "") -> None:
        from bs4 import NavigableString, Tag

        if isinstance(node, NavigableString):
            text = str(node)
            if text.strip():
                lines.append(text)
            elif text:
                lines.append(" ")
            return

        if not isinstance(node, Tag):
            return

        name = node.name.lower()

        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(f"\n{'#' * level} {text}\n\n")
            return

        if name == "p":
            lines.append("\n")
            for child in node.children:
                walk(child)
            lines.append("\n\n")
            return

        if name == "br":
            lines.append("\n")
            return

        if name in {"ul", "ol"}:
            lines.append("\n")
            for i, li in enumerate(node.find_all("li", recursive=False), start=1):
                prefix = f"{i}. " if name == "ol" else "- "
                lines.append(prefix)
                for child in li.children:
                    if getattr(child, "name", None) in {"ul", "ol"}:
                        lines.append("\n")
                        walk(child)
                    else:
                        walk(child)
                lines.append("\n")
            lines.append("\n")
            return

        if name == "blockquote":
            text = node.get_text("\n", strip=True)
            if text:
                quoted = "\n".join("> " + ln for ln in text.splitlines())
                lines.append(f"\n{quoted}\n\n")
            return

        if name in {"pre", "code"} and (name == "pre" or node.parent.name != "pre"):
            text = node.get_text()
            if name == "pre" or "\n" in text:
                lines.append(f"\n```\n{text.rstrip()}\n```\n\n")
            else:
                lines.append(f"`{text}`")
            return

        if name == "a":
            text = node.get_text(" ", strip=True)
            href = node.get("href") or ""
            abs_href = urljoin(base_url, href) if href else ""
            if text and abs_href:
                lines.append(f"[{text}]({abs_href})")
            elif text:
                lines.append(text)
            return

        if name == "img":
            src = (
                node.get("data-src")
                or node.get("data-original")
                or node.get("src")
                or ""
            )
            if src.startswith("//"):
                src = "https:" + src
            abs_src = urljoin(base_url, src) if src else ""
            alt = (node.get("alt") or "图片").strip() or "图片"
            local = url_to_local.get(abs_src)
            if local:
                lines.append(f"\n![{alt}](images/{local})\n\n")
            elif abs_src and _is_probably_image_url(abs_src):
                lines.append(f"\n![{alt}]({abs_src})\n\n")
            return

        if name in {"strong", "b"}:
            text = node.get_text("", strip=False)
            if text.strip():
                lines.append(f"**{text.strip()}**")
            return

        if name in {"em", "i"}:
            text = node.get_text("", strip=False)
            if text.strip():
                lines.append(f"*{text.strip()}*")
            return

        if name in {"hr"}:
            lines.append("\n---\n\n")
            return

        for child in node.children:
            walk(child)

    body = soup.body or soup
    walk(body)

    md = "".join(lines)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def _rewrite_markdown_images(markdown: str, url_to_local: dict[str, str]) -> str:
    """把 markdown 中仍指向远程的图片换成本地路径。"""
    if not url_to_local:
        return markdown

    def repl(match: re.Match[str]) -> str:
        alt, url = match.group(1), match.group(2)
        local = url_to_local.get(url)
        if local:
            return f"![{alt}](images/{local})"
        # 尝试去 query
        base = url.split("?")[0]
        for remote, local_name in url_to_local.items():
            if remote.split("?")[0] == base:
                return f"![{alt}](images/{local_name})"
        return match.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, markdown)


def extract_article(url: str, proxy: str | None = None, download_images: bool = True) -> ExtractedArticle:
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("请输入以 http:// 或 https:// 开头的完整网址")

    with _client(proxy) as client:
        try:
            resp = client.get(url)
        except httpx.TimeoutException as exc:
            raise ValueError("请求超时，请检查网络或稍后重试") from exc
        except httpx.RequestError as exc:
            raise ValueError(f"无法访问该网址：{exc}") from exc

        if resp.status_code >= 400:
            raise ValueError(f"网页返回错误状态码：{resp.status_code}")

        # 尽量用正确编码
        raw = resp.content
        downloaded = raw.decode(resp.encoding or "utf-8", errors="replace")
        final_url = str(resp.url)

        # trafilatura 元数据 + 正文
        meta = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            include_images=True,
            include_links=True,
            output_format="xml",
            url=final_url,
            config=_TRAFILATURA_CFG,
            favor_recall=True,
        )
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            include_links=False,
            output_format="txt",
            url=final_url,
            config=_TRAFILATURA_CFG,
            favor_recall=True,
        ) or ""

        md_from_traf = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            include_images=True,
            include_links=True,
            output_format="markdown",
            url=final_url,
            config=_TRAFILATURA_CFG,
            favor_recall=True,
        ) or ""

        metadata = trafilatura.extract_metadata(downloaded, default_url=final_url)
        title = ""
        author = ""
        date = ""
        sitename = _hostname(final_url)
        if metadata:
            title = metadata.title or ""
            author = metadata.author or ""
            date = metadata.date or ""
            sitename = metadata.sitename or sitename

        if not title:
            soup = BeautifulSoup(downloaded, "lxml")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            og = soup.find("meta", property="og:title")
            if og and og.get("content"):
                title = og["content"].strip()

        title = _clean_title(title, sitename or "")

        # 用 trafilatura 的 xml/html 片段收集图片；不够则回退整页
        content_html = ""
        if meta:
            # xml → 仍可用 soup 找 graphic/img
            content_html = meta
        if not content_html:
            content_html = downloaded

        image_urls = _collect_image_urls(content_html, final_url)
        if len(image_urls) < 3:
            # 正文图片太少时，再从整页补一些（仍有上限）
            more = _collect_image_urls(downloaded, final_url)
            for u in more:
                if u not in image_urls:
                    image_urls.append(u)

        images: list[ExtractedImage] = []
        url_to_local: dict[str, str] = {}
        if download_images and image_urls:
            images = _download_images(image_urls, client, referer=final_url)
            url_to_local = {im.original_url: im.local_name for im in images}

        # 优先用我们自己的 HTML→MD（图片路径可控）；否则改写 trafilatura markdown
        # trafilatura markdown 通常已经不错
        if md_from_traf.strip():
            markdown = _rewrite_markdown_images(md_from_traf, url_to_local)
        else:
            # 退回到简单转换
            markdown = _html_to_markdown_with_images(downloaded, final_url, url_to_local)

        if not markdown.strip() and text.strip():
            markdown = text.strip() + "\n"

        if not markdown.strip():
            raise ValueError("未能抽取到正文，可能是需要登录、反爬页面或非文章页")

        # 补全未出现在 markdown 中的本地图片（挂到文末）
        missing = [
            im for im in images
            if f"images/{im.local_name}" not in markdown
        ]
        if missing:
            markdown = markdown.rstrip() + "\n\n## 文中图片\n\n"
            for im in missing:
                markdown += f"![图片](images/{im.local_name})\n\n"

        excerpt = _excerpt_from_text(text or BeautifulSoup(markdown, "lxml").get_text(" ", strip=True))

        return ExtractedArticle(
            url=final_url,
            title=title,
            author=author or "",
            site=sitename or _hostname(final_url),
            date=date or "",
            excerpt=excerpt,
            markdown=markdown,
            text=text or BeautifulSoup(markdown, "lxml").get_text("\n", strip=True),
            images=images,
            html=content_html[:2000],  # 仅调试用，不落盘大块
        )
