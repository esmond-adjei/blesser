"""A Word (.docx) copy of a Markdown CV, laid out like the PDF (pdf_export.py metrics)."""

import io
import re
from collections.abc import Iterator

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from docx.text.paragraph import Paragraph

from api.cv import pdf_export as P
from api.cv import tables

FONT = "Arial"  # Helvetica's metric twin, present wherever Word is
INK = RGBColor(0, 0, 0)
LINK = INK
RULE = "C9D1DC"

_BULLET = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!<>|])")
# The inline marks, in the order they are tried at each position.
_TOKEN = re.compile(
    r"\[(?P<label>[^\]]+)\]\((?P<url>(?:https?://|mailto:)[^)\s]+)\)"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|<u>(?P<under>.+?)</u>"
    r"|(?<![*\w])\*(?!\s)(?P<italic>.+?)(?<!\s)\*(?![*\w])"
    r"|`(?P<code>[^`]+)`"
)


def _runs(text: str, marks: frozenset[str] = frozenset(), href: str | None = None) -> Iterator[tuple[str, frozenset[str], str | None]]:
    """(text, marks, link) pieces of one line of inline Markdown."""
    pos = 0
    for m in _TOKEN.finditer(text):
        if m.start() > pos:
            yield _ESCAPE.sub(r"\1", text[pos : m.start()]), marks, href
        if m.group("label") is not None:
            yield from _runs(m.group("label"), marks, m.group("url"))
        elif m.group("bold") is not None:
            yield from _runs(m.group("bold"), marks | {"bold"}, href)
        elif m.group("under") is not None:
            yield from _runs(m.group("under"), marks | {"underline"}, href)
        elif m.group("italic") is not None:
            yield from _runs(m.group("italic"), marks | {"italic"}, href)
        else:
            yield m.group("code"), marks | {"code"}, href
        pos = m.end()
    if pos < len(text):
        yield _ESCAPE.sub(r"\1", text[pos:]), marks, href


def _set_font(rpr_owner, size: float | None = None, bold: bool | None = None, color: RGBColor | None = INK) -> None:
    """A style's or run's font: the CV font in every script slot (no
    theme font left to override it), with size, weight and colour."""
    font = rpr_owner.font
    font.name = FONT
    rpr = rpr_owner.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for slot in ("ascii", "hAnsi", "cs", "eastAsia"):
        fonts.set(qn(f"w:{slot}"), FONT)
    for theme in ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme"):
        fonts.attrib.pop(qn(f"w:{theme}"), None)
    if size is not None:
        font.size = Pt(size)
    if bold is not None:
        font.bold = bold
        font.italic = False
    if color is not None:
        font.color.rgb = color


def _border_bottom(ppr, size_eighths: int = 5, space: int = 1) -> None:
    """A rule under a paragraph (a style's or one paragraph's pPr)."""
    for old in ppr.findall(qn("w:pBdr")):
        ppr.remove(old)
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size_eighths))
    bottom.set(qn("w:space"), str(space))
    bottom.set(qn("w:color"), RULE)
    bdr.append(bottom)
    ppr.append(bdr)


def _spacing(style, before: float, after: float, leading: float) -> None:
    pf = style.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(leading)


def _setup(doc) -> None:
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.left_margin = section.right_margin = Mm(P.MARGIN_X_MM)
    section.top_margin = section.bottom_margin = Mm(P.MARGIN_Y_MM)

    styles = doc.styles
    normal = styles["Normal"]
    _set_font(normal, P.BODY_PT)
    _spacing(normal, 0, P.BODY_AFTER, P.BODY_LEADING)

    heads = {
        "Title": (P.NAME_PT, 0, P.NAME_AFTER, P.NAME_LEADING),
        "Heading 1": (P.SECTION_PT, P.SECTION_BEFORE, P.SECTION_AFTER + 4, P.SECTION_LEADING),
        "Heading 2": (P.SUB_PT, P.SUB_BEFORE, 0, P.SUB_LEADING),
        "Heading 3": (P.SUB_PT, P.SUB_BEFORE, 0, P.SUB_LEADING),
    }
    for name, (size, before, after, leading) in heads.items():
        style = styles[name]
        _set_font(style, size, bold=True)
        _spacing(style, before, after, leading)
        style.paragraph_format.keep_with_next = True
        ppr = style.element.get_or_add_pPr()
        for old in ppr.findall(qn("w:pBdr")):
            ppr.remove(old)
    _border_bottom(styles["Heading 1"].element.get_or_add_pPr(), size_eighths=5, space=1)

    for name, indent in (
        ("List Bullet", P.BULLET_INDENT),
        ("List Bullet 2", P.BULLET2_INDENT),
        ("List Number", P.BULLET_INDENT),
        ("List Number 2", P.BULLET2_INDENT),
    ):
        style = styles[name]
        _spacing(style, 0, P.BULLET_AFTER, P.BODY_LEADING)
        style.paragraph_format.left_indent = Pt(indent + 6)


def _hyperlink(paragraph: Paragraph, url: str):
    rid = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rid)
    paragraph._p.append(link)
    return link


def _write_inline(paragraph: Paragraph, text: str) -> None:
    """Add one Markdown line's runs; a "\\n" is a line break."""
    for i, part in enumerate(text.split("\n")):
        if i:
            paragraph.add_run().add_break()
        link_el = None
        link_url = None
        for piece, marks, href in _runs(part):
            if not piece:
                continue
            run = paragraph.add_run(piece)
            run.bold = "bold" in marks or None
            run.italic = "italic" in marks or None
            run.underline = ("underline" in marks or href is not None) or None
            if "code" in marks:
                run.font.name = "Courier New"
            if href:
                run.font.color.rgb = LINK
                if link_el is None or link_url != href:
                    link_el, link_url = _hyperlink(paragraph, href), href
                link_el.append(run._r)  # moves the run into the link
            else:
                link_el = link_url = None


def _rule(doc) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = Pt(2)
    _border_bottom(p._p.get_or_add_pPr(), size_eighths=5, space=1)


_CELL_ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER, "right": WD_ALIGN_PARAGRAPH.RIGHT, None: None}


def _table(doc, table: tables.Table) -> None:
    """The table as the PDF draws it: thin rules, a shaded bold header row
    that repeats on a new page, the PDF's cell size and alignment."""
    rows = [table.header, *table.rows]
    out = doc.add_table(rows=len(rows), cols=len(table.header))
    tbl_pr = out._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), RULE)
        borders.append(el)
    tbl_pr.append(borders)
    for r, cells in enumerate(rows):
        row = out.rows[r]
        if r == 0:
            tr_pr = row._tr.get_or_add_trPr()
            repeat = OxmlElement("w:tblHeader")
            tr_pr.append(repeat)
        for c, text in enumerate(cells):
            cell = row.cells[c]
            if r == 0:
                shade = OxmlElement("w:shd")
                shade.set(qn("w:val"), "clear")
                shade.set(qn("w:fill"), "F1F4F8")
                cell._tc.get_or_add_tcPr().append(shade)
            para = cell.paragraphs[0]
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.line_spacing = Pt(P.TABLE_LEADING)
            if _CELL_ALIGN[table.align[c]] is not None:
                para.alignment = _CELL_ALIGN[table.align[c]]
            _write_inline(para, tables.unescape(text))
            for run in para.runs:
                run.font.size = Pt(P.TABLE_PT)
                if r == 0:
                    run.bold = True
    # Space after it, as the PDF leaves.
    gap = doc.add_paragraph()
    gap.paragraph_format.space_after = Pt(0)
    gap.paragraph_format.line_spacing = Pt(P.TABLE_AFTER)


def build_docx(markdown: str, title: str = "CV") -> bytes:
    doc = Document()
    _setup(doc)
    doc.core_properties.title = title
    paragraph: list[str] = []

    def flush() -> None:
        if not paragraph:
            return
        text = ""
        for i, line in enumerate(paragraph):
            if i:
                text += "\n" if paragraph[i - 1].endswith("  ") else " "
            text += line.strip()
        _write_inline(doc.add_paragraph(), text)
        paragraph.clear()

    lines = (markdown or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip():
            flush()
            continue
        if tables.starts_table(lines, i - 1):
            flush()
            table, i = tables.read_table(lines, i - 1)
            _table(doc, table)
            continue
        if P.RULE_LINE.match(line):
            flush()
            _rule(doc)
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            style = "Title" if level == 1 else f"Heading {min(level - 1, 3)}"
            _write_inline(doc.add_paragraph(style=style), heading.group(2).strip())
            continue
        bullet = _BULLET.match(line)
        if bullet:
            flush()
            ordered = bullet.group(2)[0].isdigit()
            nested = len(bullet.group(1)) >= 2
            style = ("List Number" if ordered else "List Bullet") + (" 2" if nested else "")
            _write_inline(doc.add_paragraph(style=style), line[bullet.end():].strip())
            continue
        paragraph.append(line)
    flush()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
