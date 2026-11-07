"""A simple, clean PDF of a Markdown CV.

Its page metrics are the one source for every CV page: the Word export
copies them, the webapp `.doc-sheet` thumbnails mirror them in CSS, and
`layout()` gives the editor its page breaks.
"""

import io
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from api.cv import tables
from api.exports.pdf import _inline

INK = colors.black
RULE = colors.HexColor("#c9d1dc")

# Page metrics (points unless named otherwise).
PAGE_SIZE = A4
MARGIN_X_MM = 18
MARGIN_Y_MM = 16
BODY_PT, BODY_LEADING, BODY_AFTER = 10, 14, 4
NAME_PT, NAME_LEADING, NAME_AFTER = 20, 24, 6
SECTION_PT, SECTION_LEADING, SECTION_BEFORE, SECTION_AFTER = 11.5, 15, 10, 2
SUB_PT, SUB_LEADING, SUB_BEFORE = 10.5, 14, 4
BULLET_INDENT, BULLET2_INDENT, BULLET_AFTER = 12, 24, 2
NUMBER_INDENT = 16
TABLE_PT, TABLE_LEADING, TABLE_PAD, TABLE_BEFORE, TABLE_AFTER = 9.5, 12.5, 3, 3, 6

_BULLET = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# A thematic break: three or more of the same -, * or _ (spaces allowed).
RULE_LINE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
# Underline has no Markdown mark; the editor writes <u>…</u>.
UNDERLINE = re.compile(r"<u>(.+?)</u>")


def _styles() -> dict[str, ParagraphStyle]:
    body = ParagraphStyle(
        "body", fontName="Helvetica", fontSize=BODY_PT, leading=BODY_LEADING, textColor=INK, spaceAfter=BODY_AFTER
    )
    return {
        "body": body,
        "h1": ParagraphStyle(
            "h1", parent=body, fontName="Helvetica-Bold", fontSize=NAME_PT, leading=NAME_LEADING, spaceAfter=NAME_AFTER
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=SECTION_PT,
            leading=SECTION_LEADING,
            spaceBefore=SECTION_BEFORE,
            spaceAfter=SECTION_AFTER,
        ),
        "h3": ParagraphStyle(
            "h3", parent=body, fontName="Helvetica-Bold", fontSize=SUB_PT, leading=SUB_LEADING, spaceBefore=SUB_BEFORE
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=body, leftIndent=BULLET_INDENT, bulletIndent=2, spaceAfter=BULLET_AFTER
        ),
        "bullet2": ParagraphStyle(
            "bullet2", parent=body, leftIndent=BULLET2_INDENT, bulletIndent=14, spaceAfter=BULLET_AFTER
        ),
        "number": ParagraphStyle(
            "number", parent=body, leftIndent=NUMBER_INDENT, bulletIndent=0, spaceAfter=BULLET_AFTER
        ),
        "number2": ParagraphStyle(
            "number2", parent=body, leftIndent=BULLET2_INDENT + NUMBER_INDENT - BULLET_INDENT, bulletIndent=14, spaceAfter=BULLET_AFTER
        ),
        "cell": ParagraphStyle("cell", parent=body, fontSize=TABLE_PT, leading=TABLE_LEADING, spaceAfter=0),
        "head": ParagraphStyle("head", parent=body, fontName="Helvetica-Bold", fontSize=TABLE_PT, leading=TABLE_LEADING, spaceAfter=0),
    }


def inline(text: str) -> str:
    """One line of CV Markdown as Paragraph markup: the dossier's marks
    (bold, italic, code, links) plus <u> underline."""
    # Control characters survive escaping untouched; swapped back after.
    marked = UNDERLINE.sub("\x01\\1\x02", text)
    return _inline(marked).replace('color="#10325e"', 'color="#000000"').replace("\x01", "<u>").replace("\x02", "</u>")


def _paragraph(lines: list[str]) -> str:
    """Markdown lines of one paragraph as markup: lines join with a
    space, except after a hard break (a line ending in two spaces)."""
    text = ""
    for i, line in enumerate(lines):
        if i:
            text += "\n" if lines[i - 1].endswith("  ") else " "
        text += line.strip()
    return "<br/>".join(inline(part) for part in text.split("\n"))


class _Block(Paragraph):
    """A Paragraph that knows its first source line, through page splits:
    the parts after the first are continuations."""

    cv_line = 0
    cv_continued = False

    def split(self, availWidth, availHeight):
        parts = super().split(availWidth, availHeight)
        for i, part in enumerate(parts):
            part.cv_line = self.cv_line
            part.cv_continued = self.cv_continued or i > 0
        return parts


class _TableBlock(Table):
    """A Table that knows its first source line; the parts after a page
    split are continuations (the editor shows a table whole)."""

    cv_line = 0
    cv_continued = False

    def split(self, availWidth, availHeight):
        parts = super().split(availWidth, availHeight)
        for i, part in enumerate(parts):
            part.cv_line = self.cv_line
            part.cv_continued = self.cv_continued or i > 0
        return parts


_ALIGN = {"left": "LEFT", "center": "CENTER", "right": "RIGHT", None: "LEFT"}
_TEXT_ALIGN = {"left": 0, "center": 1, "right": 2, None: 0}


def _table(table: tables.Table, styles: dict[str, ParagraphStyle]) -> _TableBlock:
    """The table across the text width, columns sized to their text (none
    under an eighth), the header row bold and repeated on a new page."""
    width = PAGE_SIZE[0] - 2 * MARGIN_X_MM * mm
    cols = len(table.header)

    def para(text: str, style: str, col: int) -> Paragraph:
        st = ParagraphStyle(f"{style}{col}", parent=styles[style], alignment=_TEXT_ALIGN[table.align[col]])
        return Paragraph(inline(tables.unescape(text)), st)

    data = [[para(c, "head", k) for k, c in enumerate(table.header)]]
    data += [[para(c, "cell", k) for k, c in enumerate(row)] for row in table.rows]
    lengths = [max(4, *(len(r[k]) for r in [table.header, *table.rows])) for k in range(cols)]
    share = [max(1 / 8, n / sum(lengths)) for n in lengths]
    col_widths = [width * s / sum(share) for s in share]
    block = _TableBlock(data, colWidths=col_widths, repeatRows=1, spaceBefore=TABLE_BEFORE, spaceAfter=TABLE_AFTER)
    block.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, RULE),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f4f8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), TABLE_PAD),
                ("BOTTOMPADDING", (0, 0), (-1, -1), TABLE_PAD + 1),
                ("LEFTPADDING", (0, 0), (-1, -1), TABLE_PAD + 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), TABLE_PAD + 2),
                *[("ALIGN", (k, 0), (k, -1), _ALIGN[a]) for k, a in enumerate(table.align)],
            ]
        )
    )
    return block


def _story(markdown: str) -> list:
    """The CV as flowables, each tagged with the 1-based source line it
    starts on (`cv_line`)."""
    styles = _styles()
    story: list = []
    paragraph: list[str] = []
    start = 0

    def add(flowable, line: int, continued: bool = False) -> None:
        flowable.cv_line = line
        flowable.cv_continued = continued
        story.append(flowable)

    def flush() -> None:
        if paragraph:
            add(_Block(_paragraph(paragraph), styles["body"]), start)
            paragraph.clear()

    lines = (markdown or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        n = i + 1
        i += 1
        if not line.strip():
            flush()
            continue
        if tables.starts_table(lines, n - 1):
            flush()
            table, i = tables.read_table(lines, n - 1)
            add(_table(table, styles), n)
            continue
        if RULE_LINE.match(line):
            flush()
            add(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=4, spaceAfter=6), n)
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            text = inline(heading.group(2).strip())
            if level == 1:
                add(_Block(text, styles["h1"]), n)
            elif level == 2:
                add(_Block(text, styles["h2"]), n)
                # The heading's rule: on a new page alone, it still
                # belongs to the heading's line.
                add(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=1, spaceAfter=4), n, continued=True)
            else:
                add(_Block(text, styles["h3"]), n)
            continue
        bullet = _BULLET.match(line)
        if bullet:
            flush()
            nested = len(bullet.group(1)) >= 2
            mark = bullet.group(2)
            if mark[0].isdigit():
                # Numbered as written: "3." stays 3.
                style = styles["number2" if nested else "number"]
                add(_Block(inline(line[bullet.end():].strip()), style, bulletText=f"{mark[:-1]}."), n)
            else:
                style = styles["bullet2" if nested else "bullet"]
                add(_Block(inline(line[bullet.end():].strip()), style, bulletText="•"), n)
            continue
        if not paragraph:
            start = n
        paragraph.append(line)
    flush()
    if not story:
        story.append(Spacer(1, 1))
    return story


class _Doc(SimpleDocTemplate):
    """Records which page each tagged flowable landed on."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.placed: list[tuple[int, int, bool]] = []

    def afterFlowable(self, flowable):
        line = getattr(flowable, "cv_line", 0)
        if line:
            self.placed.append((self.page, line, getattr(flowable, "cv_continued", False)))


def _build(markdown: str, title: str) -> tuple[bytes, _Doc]:
    buf = io.BytesIO()
    doc = _Doc(
        buf,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN_X_MM * mm,
        rightMargin=MARGIN_X_MM * mm,
        topMargin=MARGIN_Y_MM * mm,
        bottomMargin=MARGIN_Y_MM * mm,
        title=title,
    )
    doc.build(_story(markdown))
    return buf.getvalue(), doc


def build_pdf(markdown: str, title: str = "CV") -> bytes:
    return _build(markdown, title)[0]


def layout(markdown: str) -> dict:
    """Where the PDF's pages start: {"pages": n, "breaks": [{"page", "line"}]}
    with `line` the 1-based source line that opens each page after the
    first. A block split across two pages counts for the page it starts
    on, so that page's break comes before the next block."""
    _, doc = _build(markdown, "CV")
    first: dict[int, int] = {}
    for page, line, continued in doc.placed:
        if page > 1 and not continued and page not in first:
            first[page] = line
    pages = max((page for page, _, _ in doc.placed), default=1)
    return {"pages": pages, "breaks": [{"page": p, "line": first[p]} for p in sorted(first)]}
