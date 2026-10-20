"""Render the notes Markdown into a clean, styled PDF (reportlab)."""
import html
import re
import textwrap
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from notes_generator import section_meta

INK, MUTED, ACCENT = "#1B2140", "#667085", "#4F46E5"
# Built-in PDF fonts are Latin-only: swap common symbols, replace the rest with '?'
_SWAP = {"→": "->", "←": "<-", "≤": "<=", "≥": ">=", "≠": "!=", "≈": "~", "✓": "v", "✔": "v", "−": "-", "∞": "inf"}


def _clean(t: str) -> str:
    for k, v in _SWAP.items():
        t = t.replace(k, v)
    return t.encode("cp1252", "replace").decode("cp1252")


def _inline(t: str) -> str:
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r'<font face="Courier" color="#B42318">\1</font>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"(?<![\*\w])\*(?!\s)([^*]+?)(?<!\s)\*(?![\*\w])", r"<i>\1</i>", t)


def _styles() -> dict:
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=14.5,
                          textColor=colors.HexColor(INK), spaceAfter=4)
    return {
        "body": base,
        "title": ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=25),
        "meta": ParagraphStyle("m", parent=base, fontSize=9, textColor=colors.HexColor(MUTED), spaceAfter=8),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                             spaceBefore=8, spaceAfter=3, keepWithNext=1),
        "code": ParagraphStyle("c", parent=base, fontName="Courier", fontSize=8.5, leading=11.5, spaceAfter=0),
    }


def _wrap(code: str, width: int = 88) -> list:
    out = []
    for ln in code.expandtabs(4).split("\n"):
        ind = len(ln) - len(ln.lstrip())
        out += textwrap.wrap(ln, width, subsequent_indent=" " * (ind + 2)) or [""]
    return out


def _code_block(lines: list, st: dict, width: float) -> list:
    wrapped = _wrap("\n".join(lines))
    rows = [[Preformatted("\n".join(wrapped[i:i + 28]), st["code"])] for i in range(0, len(wrapped), 28)]
    t = Table(rows or [[Preformatted(" ", st["code"])]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F4FA")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D9DDEB")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [t, Spacer(1, 8)]


def _depth(stack: list, indent: int) -> int:
    while len(stack) > 1 and indent < stack[-1]:
        stack.pop()
    if indent > stack[-1]:
        stack.append(indent)
    return len(stack) - 1


def _item(text: str, depth: int, bullet: str, st: dict) -> Paragraph:
    s = ParagraphStyle(f"li{depth}", parent=st["body"], leftIndent=16 + depth * 14,
                       bulletIndent=depth * 14, spaceAfter=2.5)
    return Paragraph(_inline(text), s, bulletText=bullet)


def _page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor(ACCENT))
    canvas.rect(0, A4[1] - 6, A4[0], 6, stroke=0, fill=1)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawString(18 * mm, 10 * mm, "YouTube Notes Extractor")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(title: str, url: str, author: str, notes_md: str) -> bytes:
    st, buf = _styles(), BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title=_clean(title))
    meta = f'{html.escape(_clean(author))} | <link href="{url}" color="{ACCENT}">{url}</link>'
    flow = [Paragraph(_inline(_clean(title)), st["title"]), Paragraph(meta, st["meta"])]
    code, stack, first = None, [0], True

    for raw in _clean(notes_md).split("\n"):
        line = raw.rstrip()
        if line.strip().startswith("```"):
            if code is None:
                code = []
            else:
                flow += _code_block(code, st, doc.width)
                code = None
            continue
        if code is not None:
            code.append(raw)
            continue
        if not line.strip() or re.match(r"^-{3,}$", line.strip()):
            continue
        if m := re.match(r"^##\s+(.*)", line):
            color = section_meta(m.group(1))[1]
            head = ParagraphStyle("h2", parent=st["body"], fontName="Helvetica-Bold", fontSize=15,
                                  leading=19, textColor=colors.HexColor(color), spaceAfter=2, keepWithNext=1)
            flow += [Spacer(1, 4 if first else 12), Paragraph(_inline(m.group(1)), head),
                     HRFlowable(width="100%", thickness=1.2, color=colors.HexColor(color), spaceAfter=6)]
            first, stack = False, [0]
        elif m := re.match(r"^#{3,4}\s+(.*)", line):
            flow.append(Paragraph(_inline(m.group(1)), st["h3"]))
            stack = [0]
        elif m := re.match(r"^( *)[-*] +(.*)", line):
            d = _depth(stack, len(m.group(1)))
            flow.append(_item(m.group(2), d, "•" if d == 0 else "-", st))
        elif m := re.match(r"^( *)(\d+)[.)] +(.*)", line):
            d = _depth(stack, len(m.group(1)))
            flow.append(_item(m.group(3), d, m.group(2) + ".", st))
        else:
            flow.append(Paragraph(_inline(line.strip().lstrip("> ")), st["body"]))
            stack = [0]

    if code:  # unclosed fence
        flow += _code_block(code, st, doc.width)
    doc.build(flow, onFirstPage=_page, onLaterPages=_page)
    return buf.getvalue()
