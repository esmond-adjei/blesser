"""Branded candidate dossiers as PDF (pure reportlab: no browser or system libs).

Latin text uses Helvetica; CJK runs switch to the viewer's CID fonts so names
print instead of boxes.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ASSETS = Path(__file__).parent / "assets"

# Brand palette (webapp/src/index.css: navy-900, gold-400, mist-100).
NAVY = colors.HexColor("#10325e")
NAVY_DEEP = colors.HexColor("#0b2447")
GOLD = colors.HexColor("#eda41d")
MIST = colors.HexColor("#e8ecf0")
TINT = colors.HexColor("#f4f6f9")
INK = colors.black
MUTED = colors.black
LINE = colors.HexColor("#d5dbe3")
STRONG = colors.HexColor("#059669")
MODERATE = colors.HexColor("#f59e0b")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
BAND_H = 13 * mm

STATUS_LABELS = {
    "discovered": "Discovered",
    "researched": "Researched",
    "scored": "To review",
    "drafted": "Email drafted",
    "approved": "Approved",
    "rejected": "Passed",
    "sent": "Email sent",
}


@dataclass
class Dossier:

    id: str
    name: str
    school: str
    program: str
    status: str
    score: float | None = None
    run_title: str = ""
    rationale: str = ""
    lab: str | None = None
    bio: str | None = None
    bio_source: str | None = None
    email: str | None = None
    links: list[tuple[str, str]] = field(default_factory=list)
    papers: list[dict] = field(default_factory=list)
    draft_subject: str | None = None
    draft_body: str | None = None
    applications: list[dict] = field(default_factory=list)
    photo: bytes | None = None


_CID_FONTS = {"ja": "HeiseiKakuGo-W5", "zh": "STSong-Light", "ko": "HYGothic-Medium"}
_registered: set[str] = set()
_FALLBACK_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu")


def _font(name: str) -> str:
    if name not in _registered:
        if name in _CID_FONTS.values():
            pdfmetrics.registerFont(UnicodeCIDFont(name))
        _registered.add(name)
    return name


def _fallback_font(bold: bool = False) -> str | None:
    """A Unicode TTF for scripts Helvetica lacks (Cyrillic, Greek, ...),
    when the host has one (the API image installs DejaVu)."""
    name = "DejaVuSans-Bold" if bold else "DejaVuSans"
    if name in _registered:
        return name
    for folder in _FALLBACK_DIRS:
        path = Path(folder) / f"{name}.ttf"
        if path.exists():
            pdfmetrics.registerFont(TTFont(name, str(path)))
            _registered.add(name)
            return name
    return None if not bold else _fallback_font()


def _script(ch: str) -> str | None:
    code = ord(ch)
    if code <= 0xFF:
        return None
    if 0x3040 <= code <= 0x30FF or 0x31F0 <= code <= 0x31FF:
        return "ja"
    if 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
        return "ko"
    if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF or 0x3000 <= code <= 0x303F or 0xFF00 <= code <= 0xFFEF:
        return "han"
    try:
        ch.encode("cp1252")  # dashes, quotes, bullets: Helvetica has them
        return None
    except UnicodeEncodeError:
        return "other"


def rich(text: str | None, bold: bool = False) -> str:
    """Paragraph markup for plain text: escaped, with CJK and other non-Latin runs
    set in a font that has their glyphs."""
    if not text:
        return ""
    has_kana = any(_script(c) == "ja" for c in text)
    out: list[str] = []
    run: list[str] = []
    run_kind: str | None = None

    def flush() -> None:
        if not run:
            return
        chunk = escape("".join(run))
        font = None
        if run_kind in ("ja", "ko"):
            font = _font(_CID_FONTS[run_kind])
        elif run_kind == "han":
            # Kanji next to kana is Japanese; Han alone reads as Chinese.
            font = _font(_CID_FONTS["ja" if has_kana else "zh"])
        elif run_kind == "other":
            font = _fallback_font(bold)
        out.append(f'<font name="{font}">{chunk}</font>' if font else chunk)
        run.clear()

    for ch in text:
        kind = _script(ch)
        if kind != run_kind:
            flush()
            run_kind = kind
        run.append(ch)
    flush()
    return "".join(out)


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])")
_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def markdown_paragraphs(text: str | None, style: ParagraphStyle, bullet: ParagraphStyle) -> list:
    """The small Markdown agents write (paragraphs, bullets, bold, italics, code, links)."""
    if not text:
        return []
    flowables: list = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if lines and all(re.match(r"^\s*([-*•]|\d+[.)])\s+", ln) for ln in lines):
            for ln in lines:
                item = re.sub(r"^\s*([-*•]|\d+[.)])\s+", "", ln)
                flowables.append(Paragraph(_inline(item), bullet, bulletText="•"))
            continue
        joined = " ".join(ln.strip() for ln in lines)
        joined = re.sub(r"^#+\s*", "", joined)
        flowables.append(Paragraph(_inline(joined), style))
    return flowables


def _inline(text: str) -> str:
    links: list[tuple[str, str]] = []

    def keep_link(m: re.Match) -> str:
        links.append((m.group(1), m.group(2)))
        return f"\x00{len(links) - 1}\x00"

    marked = _LINK.sub(keep_link, text)
    html = rich(marked)
    html = _BOLD.sub(r"<b>\1</b>", html)
    html = _ITALIC.sub(r"<i>\1</i>", html)
    html = _CODE.sub(r'<font name="Courier">\1</font>', html)
    for i, (label, url) in enumerate(links):
        html = html.replace(
            f"\x00{i}\x00",
            f'<link href="{escape(url, {chr(34): "&quot;"})}" color="#000000"><u>{rich(label)}</u></link>',
        )
    return html


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=10, leading=14.5, textColor=INK)
    return {
        "body": base,
        "muted": ParagraphStyle("muted", parent=base, fontSize=8.5, leading=12, textColor=MUTED),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=12, bulletIndent=2, spaceAfter=2),
        "name": ParagraphStyle("name", parent=base, fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=INK),
        "place": ParagraphStyle("place", parent=base, fontSize=11, leading=15, textColor=MUTED),
        "section": ParagraphStyle("section", parent=base, fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=INK),
        "paper": ParagraphStyle("paper", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13.5),
        "abstract": ParagraphStyle("abstract", parent=base, fontSize=8.5, leading=12, textColor=MUTED),
        "subject": ParagraphStyle("subject", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14),
        "email": ParagraphStyle("email", parent=base, fontSize=9.5, leading=14),
        "cell": ParagraphStyle("cell", parent=base, fontSize=9, leading=12.5),
        "cell_label": ParagraphStyle("cell_label", parent=base, fontSize=8, leading=11, textColor=MUTED),
        "cover_title": ParagraphStyle("cover_title", parent=base, fontName="Helvetica-Bold", fontSize=34, leading=40, textColor=colors.white),
        "cover_sub": ParagraphStyle("cover_sub", parent=base, fontSize=13, leading=18, textColor=MIST),
        "toc_title": ParagraphStyle("toc_title", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=INK),
        "toc": ParagraphStyle("toc", parent=base, fontSize=10, leading=13),
        "toc_head": ParagraphStyle("toc_head", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=MUTED),
        "pill": ParagraphStyle("pill", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=TA_CENTER),
    }


def score_band(score: float | None) -> tuple[float | None, str, colors.Color]:
    """(percent, label, colour) with the web app's ScoreBar thresholds."""
    if score is None:
        return None, "Not scored", MUTED
    pct = score * 100 if score <= 1 else score
    if pct >= 70:
        return pct, "Strong match", STRONG
    if pct >= 45:
        return pct, "Moderate match", MODERATE
    return pct, "Weak match", MUTED


class ScoreRing(Flowable):

    def __init__(self, score: float | None, size: float = 25 * mm):
        super().__init__()
        self.score = score
        self.size = size
        self.width = size
        self.height = size + 5 * mm

    def draw(self) -> None:
        c = self.canv
        pct, label, colour = score_band(self.score)
        r = self.size / 2 - 2
        cx, cy = self.size / 2, 5 * mm + self.size / 2
        c.setLineWidth(5)
        c.setStrokeColor(MIST)
        c.circle(cx, cy, r, stroke=1, fill=0)
        if pct is not None and pct > 0:
            c.setStrokeColor(colour)
            c.setLineCap(1)
            sweep = -360 * min(pct, 100) / 100
            path = c.beginPath()
            path.arc(cx - r, cy - r, cx + r, cy + r, startAng=90, extent=sweep)
            c.drawPath(path, stroke=1, fill=0)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(cx, cy - 3, f"{pct:.0f}%" if pct is not None else "–")
        c.setFillColor(colour if pct is not None else MUTED)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(cx, 1.2 * mm, label.upper())


class Portrait(Flowable):
    """The professor's photo in a circle, or their initials on navy."""

    def __init__(self, name: str, photo: bytes | None, size: float = 25 * mm):
        super().__init__()
        self.name = name
        self.photo = photo
        self.width = self.height = size

    def draw(self) -> None:
        c = self.canv
        s = self.width
        image = None
        if self.photo:
            try:
                image = ImageReader(io.BytesIO(self.photo))
            except Exception:  # noqa: BLE001 - a bad image falls back to initials
                image = None
        if image is not None:
            c.saveState()
            path = c.beginPath()
            path.circle(s / 2, s / 2, s / 2)
            c.clipPath(path, stroke=0, fill=0)
            c.drawImage(image, 0, 0, s, s, preserveAspectRatio=False, mask="auto")
            c.restoreState()
            c.setStrokeColor(MIST)
            c.setLineWidth(2)
            c.circle(s / 2, s / 2, s / 2 - 1, stroke=1, fill=0)
            return
        c.setFillColor(NAVY)
        c.circle(s / 2, s / 2, s / 2, stroke=0, fill=1)
        words = self.name.split()
        initials = "".join(w[0] for w in words[:2] if w).upper() or "?"
        font = "Helvetica-Bold"
        kind = _script(initials[0])
        if kind is not None:
            # A CJK name's first character, in a font that has it.
            initials = self.name.strip()[:1]
            font = (
                _font(_CID_FONTS["ja" if kind == "ja" else "ko" if kind == "ko" else "zh"])
                if kind != "other"
                else _fallback_font()
            )
        if font:
            c.setFillColor(colors.white)
            c.setFont(font, s * 0.36)
            c.drawCentredString(s / 2, s / 2 - s * 0.13, initials)


class SectionTitle(Flowable):
    """A small-caps heading with the gold accent the app uses."""

    def __init__(self, text: str, width: float):
        super().__init__()
        self.text = text.upper()
        self.width = width
        self.height = 8 * mm

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(GOLD)
        c.roundRect(0, 2.4 * mm, 3.2 * mm, 3.2 * mm, 0.8 * mm, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(5.5 * mm, 2.9 * mm, self.text)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        text_w = pdfmetrics.stringWidth(self.text, "Helvetica-Bold", 9)
        c.line(5.5 * mm + text_w + 3 * mm, 4 * mm, self.width, 4 * mm)


class Anchor(Flowable):
    """An invisible link target and outline entry, noting its page."""

    def __init__(self, key: str, title: str, pages: dict[str, int]):
        super().__init__()
        self.key = key
        self.title = title
        self.pages = pages
        self.width = self.height = 0

    def draw(self) -> None:
        self.canv.bookmarkPage(self.key)
        self.canv.addOutlineEntry(self.title, self.key, level=0)
        self.pages[self.key] = self.canv.getPageNumber()


def _pill(text: str, fg: colors.Color, bg: colors.Color, styles) -> Table:
    style = ParagraphStyle("p", parent=styles["pill"], textColor=fg)
    width = pdfmetrics.stringWidth(text, "Helvetica-Bold", 8) + 6 * mm
    t = Table([[Paragraph(escape(text), style)]], colWidths=[width], rowHeights=[5.6 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("ROUNDEDCORNERS", [2.8 * mm] * 4),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    return t


def _pills(items: list[Table]) -> Table:
    t = Table([items], colWidths=[i._colWidths[0] + 2 * mm for i in items], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return t


def _status_colors(status: str) -> tuple[colors.Color, colors.Color]:
    if status in ("approved", "sent"):
        return STRONG, colors.HexColor("#d1fae5")
    if status == "rejected":
        return colors.HexColor("#b42318"), colors.HexColor("#fee4e2")
    if status == "drafted":
        return NAVY, colors.HexColor("#dbeafe")
    return MUTED, MIST


_LINK_SCHEMES = ("https://", "http://", "mailto:")


def _href(url: str | None) -> str | None:
    """A stored URL as a link target, only for web and mail links: a PDF
    viewer would otherwise offer javascript: or file: links as clickable."""
    if not url or not url.strip().lower().startswith(_LINK_SCHEMES):
        return None
    return escape(url.strip(), {'"': "&quot;"})


def _link(label: str, url: str) -> str:
    href = _href(url)
    if href is None:
        return rich(label)
    return f'<link href="{href}" color="#000000"><u>{rich(label)}</u></link>'


def candidate_flowables(d: Dossier, styles, width: float, pages: dict[str, int]) -> list:
    out: list = [Anchor(f"c-{d.id}", d.name, pages)]

    head_text = [Paragraph(rich(d.name, bold=True), styles["name"])]
    place = " · ".join(x for x in (d.school, d.program) if x)
    if place:
        head_text.append(Paragraph(rich(place), styles["place"]))
    pills = [_pill(STATUS_LABELS.get(d.status, d.status.title()), *_status_colors(d.status), styles)]
    if d.lab:
        pills.append(_pill(d.lab[:48], NAVY, TINT, styles))
    head_text += [Spacer(1, 2.5 * mm), _pills(pills)]
    if d.run_title:
        head_text += [Spacer(1, 2 * mm), Paragraph(f"From the run {rich(d.run_title)}", styles["muted"])]

    header = Table(
        [[Portrait(d.name, d.photo), head_text, ScoreRing(d.score)]],
        colWidths=[31 * mm, width - 31 * mm - 30 * mm, 30 * mm],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ]
        )
    )
    out += [header, Spacer(1, 5 * mm)]

    contact = []
    if d.email:
        contact.append(_link(d.email, f"mailto:{d.email}"))
    contact += [_link(label, url) for label, url in d.links]
    if contact:
        strip = Table(
            [[Paragraph("  ·  ".join(contact), styles["cell"])]],
            colWidths=[width],
        )
        strip.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), TINT),
                    ("ROUNDEDCORNERS", [2 * mm] * 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.6 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8 * mm),
                ]
            )
        )
        out += [strip, Spacer(1, 4 * mm)]

    if d.rationale:
        out.append(
            KeepTogether(
                [SectionTitle("Why this match", width)]
                + markdown_paragraphs(d.rationale, styles["body"], styles["bullet"])[:1]
            )
        )
        out += markdown_paragraphs(d.rationale, styles["body"], styles["bullet"])[1:]
        out.append(Spacer(1, 3 * mm))

    if d.bio:
        source = (
            "From their faculty page."
            if d.bio_source == "faculty"
            else "Summarized from their papers."
            if d.bio_source
            else ""
        )
        block = [SectionTitle("About", width), Paragraph(rich(d.bio), styles["body"])]
        if source:
            block += [Spacer(1, 1 * mm), Paragraph(source, styles["muted"])]
        out += [KeepTogether(block), Spacer(1, 3 * mm)]

    if d.papers:
        out.append(CondPageBreak(30 * mm))
        out.append(SectionTitle(f"Cited papers ({len(d.papers)})", width))
        for i, p in enumerate(d.papers, 1):
            title = rich(p.get("title") or "Untitled", bold=True)
            href = _href(p.get("url"))
            if href:
                title = f'<link href="{href}" color="#14233a">{title}</link>'
            meta = escape(str(p.get("year") or "Year unknown"))
            rows = [
                Paragraph(f'<font color="#eda41d">{i:02d}</font>&nbsp;&nbsp;{title}', styles["paper"]),
                Paragraph(meta + ("  ·  " + _link("Open", p["url"]) if href else ""), styles["muted"]),
            ]
            abstract = (p.get("abstract") or "").strip()
            if abstract:
                cut = abstract if len(abstract) <= 480 else abstract[:480].rsplit(" ", 1)[0] + "…"
                rows += [Spacer(1, 1 * mm), Paragraph(rich(cut), styles["abstract"])]
            out += [KeepTogether(rows), Spacer(1, 3 * mm)]

    for app in d.applications:
        out.append(CondPageBreak(40 * mm))
        out.append(SectionTitle("Application", width))
        out.append(_application_table(app, styles, width))
        out.append(Spacer(1, 4 * mm))

    if d.draft_subject or d.draft_body:
        out.append(CondPageBreak(45 * mm))
        out.append(SectionTitle("Outreach email", width))
        body = [Paragraph(rich(d.draft_subject or "(no subject)", bold=True), styles["subject"]), Spacer(1, 2 * mm)]
        for para in re.split(r"\n\s*\n", (d.draft_body or "").strip()):
            body.append(Paragraph(rich(para).replace("\n", "<br/>"), styles["email"]))
            body.append(Spacer(1, 2 * mm))
        box = Table([[body]], colWidths=[width])
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), TINT),
                    ("LINEBEFORE", (0, 0), (0, -1), 2.2, GOLD),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 4 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
                ]
            )
        )
        out.append(box)
    return out


def _application_table(app: dict, styles, width: float) -> Table:
    def row(label: str, value: str) -> list:
        return [Paragraph(label, styles["cell_label"]), Paragraph(value, styles["cell"])]

    rows = [row("Programme", rich(" · ".join(x for x in (app.get("school"), app.get("program")) if x)))]
    if app.get("deadline"):
        rows.append(row("Deadline", rich(app["deadline"])))
    rows.append(row("Status", rich((app.get("status") or "").replace("_", " ").capitalize())))
    waiver = "Available" if app.get("fee_waiver") else "None found"
    if app.get("fee_waiver_notes"):
        waiver += f" · {rich(app['fee_waiver_notes'])}"
    else:
        waiver = rich(waiver)
    rows.append(row("Fee waiver", waiver))
    reqs = app.get("requirements") or []
    if reqs:
        items = [
            (
                '<font color="#059669"><b>DONE</b></font>'
                if r.get("done")
                else '<font color="#b26b00"><b>TO DO</b></font>'
            )
            + f"&nbsp;&nbsp;{rich(r.get('label') or '')}"
            for r in reqs
            if isinstance(r, dict)
        ]
        rows.append(row("Requirements", "<br/>".join(items)))
    if app.get("link"):
        rows.append(row("Admissions", _link(app["link"], app["link"])))
    t = Table(rows, colWidths=[30 * mm, width - 30 * mm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
            ]
        )
    )
    return t


class _NumberedCanvas(pdf_canvas.Canvas):
    """Holds pages until the end so the footer can say "of N"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved: list[dict] = []

    def showPage(self) -> None:
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            if state.get("_branded", True):
                self.setFont("Helvetica", 7.5)
                self.setFillColor(MUTED)
                self.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def _draw_band(c, subtitle: str) -> None:
    c.saveState()
    c.setFillColor(NAVY)
    c.rect(0, PAGE_H - BAND_H, PAGE_W, BAND_H, stroke=0, fill=1)
    c.setFillColor(GOLD)
    c.rect(0, PAGE_H - BAND_H - 0.8 * mm, PAGE_W, 0.8 * mm, stroke=0, fill=1)
    logo = ASSETS / "logo-on-navy.png"
    c.drawImage(str(logo), MARGIN, PAGE_H - BAND_H + 2.5 * mm, 8 * mm, 8 * mm, mask="auto")
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN + 10 * mm, PAGE_H - BAND_H + 4.6 * mm, "Graduator")
    # The subtitle is often a name: set it as markup so any script gets glyphs.
    style = ParagraphStyle("band", fontName="Helvetica", fontSize=8.5, leading=10, textColor=MIST, alignment=TA_RIGHT)
    p = Paragraph(rich(subtitle), style)
    p.wrap(PAGE_W / 2, BAND_H)
    p.drawOn(c, PAGE_W / 2 - MARGIN, PAGE_H - BAND_H + 4.4 * mm)
    c.restoreState()


def _draw_footer(c, prepared: str) -> None:
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
    style = ParagraphStyle("foot", fontName="Helvetica", fontSize=7.5, leading=9, textColor=MUTED)
    p = Paragraph(rich(prepared), style)
    p.wrap(PAGE_W - 2 * MARGIN - 30 * mm, 10 * mm)
    p.drawOn(c, MARGIN, 9.6 * mm)
    c.restoreState()


def _draw_cover(c, title: str, subtitle: str, prepared: str) -> None:
    c.saveState()
    c.setFillColor(NAVY)
    c.rect(0, PAGE_H * 0.42, PAGE_W, PAGE_H * 0.58, stroke=0, fill=1)
    c.setFillColor(NAVY_DEEP)
    path = c.beginPath()
    path.moveTo(0, PAGE_H * 0.42)
    path.lineTo(PAGE_W, PAGE_H * 0.42)
    path.lineTo(PAGE_W, PAGE_H * 0.56)
    path.close()
    c.drawPath(path, stroke=0, fill=1)
    c.setFillColor(GOLD)
    c.rect(0, PAGE_H * 0.42 - 1.6 * mm, PAGE_W, 1.6 * mm, stroke=0, fill=1)
    c.drawImage(str(ASSETS / "logo-on-navy.png"), MARGIN, PAGE_H - 52 * mm, 26 * mm, 26 * mm, mask="auto")
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN + 30 * mm, PAGE_H - 38 * mm, "Graduator")
    c.drawImage(str(ASSETS / "gradis.png"), PAGE_W - MARGIN - 52 * mm, 30 * mm, 52 * mm, 52 * mm, mask="auto")
    c.restoreState()
    frame_top = PAGE_H * 0.42 + 70 * mm
    styles = _styles()
    t = Paragraph(rich(title), styles["cover_title"])
    s = Paragraph(rich(subtitle), styles["cover_sub"])
    w = PAGE_W - 2 * MARGIN
    for flow, gap in ((t, 0), (s, 6 * mm)):
        _, h = flow.wrap(w, PAGE_H)
        frame_top -= h + gap
        flow.drawOn(c, MARGIN, frame_top)
    for text, y in ((prepared, 40 * mm), (DISCLAIMER, 30 * mm)):
        p = Paragraph(rich(text), styles["muted"])
        p.wrap(w - 60 * mm, PAGE_H)
        p.drawOn(c, MARGIN, y)


def build_pdf(
    dossiers: list[Dossier],
    *,
    title: str,
    subtitle: str,
    prepared: str,
) -> bytes:
    styles = _styles()
    width = PAGE_W - 2 * MARGIN
    several = len(dossiers) > 1

    def render(pages: dict[str, int], known: dict[str, int]) -> bytes:
        buf = io.BytesIO()
        doc = BaseDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=BAND_H + 10 * mm,
            bottomMargin=20 * mm,
            title=title,
            author="Graduator",
            subject=subtitle,
            creator="Graduator",
        )
        body_frame = Frame(MARGIN, 20 * mm, width, PAGE_H - BAND_H - 30 * mm, id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        cover_frame = Frame(MARGIN, 20 * mm, width, 10 * mm, id="cover")

        def on_body(c, _doc):
            c._branded = True
            _draw_band(c, title)
            _draw_footer(c, prepared)

        def on_cover(c, _doc):
            c._branded = False
            _draw_cover(c, title, subtitle, prepared)

        templates = [PageTemplate(id="body", frames=[body_frame], onPage=on_body)]
        story: list = []
        if several:
            templates.insert(0, PageTemplate(id="cover", frames=[cover_frame], onPage=on_cover))
            story += [NextPageTemplate("body"), PageBreak()]
            story += _contents(dossiers, styles, width, known)
            story.append(PageBreak())
        doc.addPageTemplates(templates)
        for i, d in enumerate(dossiers):
            if i:
                story.append(PageBreak())
            story += candidate_flowables(d, styles, width, pages)
        if not several:
            story += [Spacer(1, 8 * mm), Paragraph(DISCLAIMER, styles["muted"])]
        doc.build(story, canvasmaker=_NumberedCanvas)
        return buf.getvalue()

    if not several:
        return render({}, {})
    # Two passes: the first learns each candidate's start page for the contents.
    first: dict[str, int] = {}
    render(first, {})
    return render({}, first)


def _contents(dossiers: list[Dossier], styles, width: float, known: dict[str, int]) -> list:
    rows = [
        [
            Paragraph("#", styles["toc_head"]),
            Paragraph("PROFESSOR", styles["toc_head"]),
            Paragraph("SCHOOL", styles["toc_head"]),
            Paragraph("MATCH", styles["toc_head"]),
            Paragraph("PAGE", styles["toc_head"]),
        ]
    ]
    for i, d in enumerate(dossiers, 1):
        pct, label, colour = score_band(d.score)
        hexc = colour.hexval().replace("0x", "#")
        rows.append(
            [
                Paragraph(f'<font color="#eda41d">{i:02d}</font>', styles["toc"]),
                Paragraph(f'<link destination="c-{d.id}" color="#000000"><b>{rich(d.name, bold=True)}</b></link>', styles["toc"]),
                Paragraph(rich(d.school), styles["toc"]),
                Paragraph(f'<font color="{hexc}"><b>{f"{pct:.0f}%" if pct is not None else "–"}</b></font> <font size="8" color="#5b6b80">{label}</font>', styles["toc"]),
                Paragraph(f'<link destination="c-{d.id}">{known.get(f"c-{d.id}", "")}</link>', styles["toc"]),
            ]
        )
    table = Table(rows, colWidths=[10 * mm, width * 0.36, width * 0.32, width * 0.2, None], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, NAVY),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TINT]),
                ("TOPPADDING", (0, 0), (-1, -1), 2.4 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4 * mm),
                ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    return [
        Paragraph("Contents", styles["toc_title"]),
        Spacer(1, 2 * mm),
        Paragraph(
            f"{len(dossiers)} professors, strongest matches first. Names link to their pages.",
            styles["muted"],
        ),
        Spacer(1, 6 * mm),
        table,
        Spacer(1, 8 * mm),
        Paragraph(DISCLAIMER, styles["muted"]),
    ]


def prepared_line(owner: str, when: datetime) -> str:
    return f"Prepared for {owner} · {when:%d %B %Y}"


DISCLAIMER = (
    "Scores, summaries and drafts are AI-assisted from public sources. "
    "Check them against the professor's own pages before you rely on them."
)

