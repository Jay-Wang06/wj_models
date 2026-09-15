"""将剪藏 Markdown 导出为 PDF（支持中文）。"""
from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF


def _find_chinese_font() -> Path | None:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttf"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _strip_md_inline(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[`*_~#>]+", "", text)
    return text


class ClipPDF(FPDF):
    def footer(self) -> None:  # noqa: D401
        self.set_y(-15)
        self.set_font("ClipFont", size=9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"{self.page_no()}", align="C")


def markdown_to_pdf(md_path: Path, pdf_path: Path, images_dir: Path | None = None) -> Path:
    font_path = _find_chinese_font()
    if not font_path:
        raise RuntimeError(
            "未找到可用的中文字体。Windows 通常自带微软雅黑（msyh.ttc）；"
            "请安装中文字体后重试。"
        )

    text = md_path.read_text(encoding="utf-8")
    pdf = ClipPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    # ttc 需要 uni=True；fpdf2 用 add_font
    pdf.add_font("ClipFont", fname=str(font_path))
    pdf.set_font("ClipFont", size=12)

    effective_width = pdf.w - pdf.l_margin - pdf.r_margin
    in_code = False
    code_lines: list[str] = []

    def flush_code() -> None:
        nonlocal code_lines
        if not code_lines:
            return
        pdf.set_font("ClipFont", size=9)
        pdf.set_fill_color(245, 245, 248)
        block = "\n".join(code_lines)
        pdf.multi_cell(effective_width, 5, block, fill=True)
        pdf.ln(2)
        pdf.set_font("ClipFont", size=12)
        code_lines = []

    def write_paragraph(content: str, size: int = 12, skip_after: float = 3) -> None:
        content = content.strip()
        if not content:
            return
        pdf.set_font("ClipFont", size=size)
        pdf.multi_cell(effective_width, size * 0.55 + 2, content)
        pdf.ln(skip_after)

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if line.strip().startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
                code_lines = []
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not line.strip():
            pdf.ln(2)
            continue

        # 图片
        img_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line.strip())
        if img_match:
            alt, src = img_match.group(1), img_match.group(2)
            img_file: Path | None = None
            if src.startswith("images/") and images_dir:
                img_file = images_dir / src.split("/", 1)[1]
            elif images_dir and not src.startswith(("http://", "https://")):
                candidate = images_dir / Path(src).name
                if candidate.exists():
                    img_file = candidate
            if img_file and img_file.exists() and img_file.suffix.lower() in {
                ".jpg", ".jpeg", ".png", ".gif",
            }:
                try:
                    # 控制宽度
                    max_w = effective_width
                    pdf.image(str(img_file), w=min(max_w, 160))
                    pdf.ln(4)
                    continue
                except Exception:  # noqa: BLE001
                    write_paragraph(f"[图片: {alt or img_file.name}]")
                    continue
            write_paragraph(f"[图片: {alt or src}]")
            continue

        if line.startswith("# "):
            write_paragraph(_strip_md_inline(line[2:]), size=20, skip_after=6)
            continue
        if line.startswith("## "):
            write_paragraph(_strip_md_inline(line[3:]), size=16, skip_after=4)
            continue
        if line.startswith("### "):
            write_paragraph(_strip_md_inline(line[4:]), size=14, skip_after=3)
            continue
        if line.startswith(">"):
            quote = _strip_md_inline(line.lstrip("> ").strip())
            pdf.set_text_color(90, 90, 110)
            write_paragraph(quote, size=11, skip_after=2)
            pdf.set_text_color(0, 0, 0)
            continue
        if re.match(r"^[-*]\s+", line):
            write_paragraph("• " + _strip_md_inline(re.sub(r"^[-*]\s+", "", line)))
            continue
        if re.match(r"^\d+\.\s+", line):
            write_paragraph(_strip_md_inline(line))
            continue
        if line.strip() == "---":
            pdf.ln(2)
            y = pdf.get_y()
            pdf.set_draw_color(200, 200, 210)
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(4)
            continue

        write_paragraph(_strip_md_inline(line))

    if in_code:
        flush_code()

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))
    return pdf_path
