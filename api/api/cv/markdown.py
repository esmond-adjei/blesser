"""CV text as Markdown: built once from an upload (DOCX units or PDF
text lines), then the base CV the student edits. Pure functions."""

import re

from api.cv import tables

#: Headings a CV commonly uses, for text with no heading style.
_SECTION_WORDS = (
    "education", "experience", "work experience", "research experience",
    "professional experience", "employment", "publications", "projects",
    "skills", "technical skills", "awards", "honors", "honours",
    "certifications", "activities", "leadership", "volunteering",
    "teaching", "teaching experience", "references", "summary", "profile",
    "objective", "interests", "research interests", "languages",
    "presentations", "talks", "grants", "scholarships", "coursework",
    "achievements", "contact",
)

# Bullet glyphs, including the private-use ones Symbol and Wingdings
# bullets come out as when Word exports a PDF.
_BULLET = re.compile(
    r"^\s*(?:[-*+•●▪◦‣⁃–—·■➢→]"
    r"|\d{1,2}[.)])\s+"
)
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s*)?\d{1,3}(?:\s*(?:/|of)\s*\d{1,3})?\s*$", re.IGNORECASE)


#: Heading keyword -> section, for readers that want one kind of section
#: (first match wins, so "research experience" counts as experience).
SECTION_KEYWORDS = (
    ("education", "education"),
    ("experience", "experience"),
    ("employment", "experience"),
    ("work history", "experience"),
    ("skills", "skills"),
    ("technical skills", "skills"),
    ("publications", "publications"),
    ("research", "research"),
    ("projects", "projects"),
    ("awards", "awards"),
    ("honors", "awards"),
    ("teaching", "teaching"),
    ("grants", "grants"),
    ("service", "service"),
    ("summary", "summary"),
    ("objective", "summary"),
    ("references", "references"),
    ("coursework", "education"),
)


def section_hint(heading_text: str) -> tuple[str | None, float | None]:
    """(section, confidence) for a heading's text, or (None, None)."""
    text = re.sub(r"\s+", " ", heading_text or "").strip().lower()
    for keyword, hint in SECTION_KEYWORDS:
        if keyword in text:
            return hint, 0.7
    return None, None


def _clean(text: str) -> str:
    """One unit's text on one Markdown line: tab runs become a dash
    separator ("Engineer<TAB>2021" reads "Engineer — 2021"), line breaks
    become hard breaks, stray spaces collapse."""
    text = re.sub(r"[  ]+", " ", text or "")
    text = re.sub(r"\s*\t[\t ]*", " — ", text.strip())
    lines = [line.strip() for line in text.split("\n")]
    return "  \n".join(line for line in lines if line)


def _is_section_word(text: str) -> bool:
    return text.strip().rstrip(":").lower() in _SECTION_WORDS


_CELL_PATH = re.compile(r"^(?P<table>.*?tbl\[\d+\])/tr\[(?P<row>\d+)\]/tc\[(?P<col>\d+)\]")
#: More paragraphs than this in one cell: the table lays the page out
#: (a CV's two-column header, say), so its text stays paragraphs.
_LAYOUT_CELL_PARAGRAPHS = 2


def _data_table(cells: dict[tuple[int, int], list[str]]) -> str | None:
    """A Word table's cells as a Markdown table, when it holds data: at
    least two rows and two columns, a paragraph or two per cell."""
    if not cells:
        return None
    rows = 1 + max(r for r, _ in cells)
    cols = 1 + max(c for _, c in cells)
    if rows < 2 or cols < 2 or any(len(texts) > _LAYOUT_CELL_PARAGRAPHS for texts in cells.values()):
        return None
    grid = [[" ".join(cells.get((r, c), [])) for c in range(cols)] for r in range(rows)]
    return tables.write_table(grid)


def units_to_markdown(units: list) -> str:
    """Units in reading order (headers first, then the body, then footers)
    to Markdown. Accepts EditableUnit models or their dicts."""

    def field(u, name):
        return u.get(name) if isinstance(u, dict) else getattr(u, name, None)

    def part(u) -> str:
        source = field(u, "source") or {}
        return (source.get("part") if isinstance(source, dict) else getattr(source, "part", "")) or ""

    ordered = sorted(
        units,
        key=lambda u: (0 if "/header" in part(u) else 2 if "/footer" in part(u) else 1),
    )
    blocks: list[str] = []
    bullets: list[str] = []
    # The Word table being read: its path, its cells' text, and its units
    # (written as paragraphs if it turns out to be a layout table).
    table: dict = {"key": None, "cells": {}, "units": []}

    def flush_bullets():
        if bullets:
            blocks.append("\n".join(bullets))
            bullets.clear()

    def source_path(u) -> str:
        source = field(u, "source") or {}
        return (source.get("path") if isinstance(source, dict) else getattr(source, "path", "")) or ""

    def add(u) -> None:
        kind = field(u, "type")
        text = _clean(field(u, "text") or "")
        if kind == "image" or not text:
            return
        if "/footer" in part(u) and _PAGE_NUMBER.match(text):
            return
        if kind == "bullet":
            bullets.append("- " + _BULLET.sub("", text))
            return
        flush_bullets()
        if kind == "heading":
            level = field(u, "heading_level") or 2
            blocks.append("#" * max(1, min(level, 6)) + " " + text)
        elif _is_section_word(text) and len(text) <= 40:
            blocks.append("## " + text.rstrip(":"))
        else:
            blocks.append(text)

    def flush_table() -> None:
        if table["key"] is None:
            return
        written = _data_table(table["cells"])
        units_in, table["key"], table["cells"], table["units"] = table["units"], None, {}, []
        if written is None:
            for unit in units_in:
                add(unit)
        else:
            flush_bullets()
            blocks.append(written)

    for u in ordered:
        cell = _CELL_PATH.match(source_path(u)) if field(u, "type") == "table_cell" else None
        if cell is None:
            flush_table()
            add(u)
            continue
        key = (part(u), cell.group("table"))
        if key != table["key"]:
            flush_table()
            table["key"] = key
        table["units"].append(u)
        text = _clean(field(u, "text") or "")
        if text:
            table["cells"].setdefault((int(cell.group("row")), int(cell.group("col"))), []).append(text)
    flush_table()
    flush_bullets()
    return _finish(blocks)


def pdf_text_to_markdown(pages: list[str]) -> str:
    """Text extracted from a PDF, one string per page, to Markdown. A known
    section word or a short all-caps line becomes a heading; a bullet glyph
    starts a bullet that its indented following lines continue."""
    blocks: list[str] = []
    current: list[str] = []
    bullet: list[str] | None = None

    def end_paragraph():
        nonlocal bullet
        if bullet is not None:
            current.append("- " + " ".join(bullet))
            bullet = None
        if current:
            blocks.append("\n".join(current))
            current.clear()

    for page in pages:
        for raw in (page or "").splitlines():
            line = re.sub(r"\s+", " ", raw).strip()
            if not line:
                end_paragraph()
                continue
            if _PAGE_NUMBER.match(line):
                continue
            words = line.split(" ")
            caps = line.upper() == line and any(ch.isalpha() for ch in line)
            if _is_section_word(line) or (caps and len(words) <= 4 and len(line) <= 40):
                end_paragraph()
                blocks.append("## " + line.rstrip(":").title() if caps else "## " + line.rstrip(":"))
                continue
            if _BULLET.match(line):
                if bullet is not None:
                    current.append("- " + " ".join(bullet))
                bullet = [_BULLET.sub("", line)]
                continue
            if bullet is not None and raw[:1].isspace():
                bullet.append(line)
                continue
            if bullet is not None:
                current.append("- " + " ".join(bullet))
                bullet = None
            current.append(line)
        end_paragraph()
    if blocks and not blocks[0].startswith("#"):
        first, _, rest = blocks[0].partition("\n")
        if len(first) <= 60 and not _BULLET.match(first):
            # The first short line of a CV is almost always the name.
            blocks[0] = "# " + first + ("\n\n" + rest if rest else "")
    return _finish(blocks)


def _finish(blocks: list[str]) -> str:
    return "\n\n".join(b for b in blocks if b.strip()).strip() + "\n"


_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_EMPHASIS = re.compile(r"(\*\*|__|\*|_|`)(?=\S)(.+?)(?<=\S)\1")


def to_plain_text(markdown: str) -> str:
    """Markdown without its marks: headings plain, bullets as "•", links
    as "text (url)", emphasis and <u> underline dropped, hard breaks as
    line breaks."""
    out = []
    for line in (markdown or "").splitlines():
        # A table's rows: cells apart by tabs, no delimiter row.
        if re.match(r"^\s*\|.*\|\s*$", line):
            if tables.is_delimiter_row(line):
                continue
            line = "\t".join(tables.split_row(line))
        line = line.rstrip()
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^(\s*)[-*+]\s+", r"\1• ", line)
        line = _LINK.sub(lambda m: m.group(1) if m.group(1) == m.group(2) else f"{m.group(1)} ({m.group(2)})", line)
        line = _EMPHASIS.sub(r"\2", line)
        line = re.sub(r"</?u>", "", line)
        line = line.replace("\\", "")
        out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def sections(markdown: str) -> list[tuple[str, str]]:
    """(heading, body) per heading, in order; text before the first
    heading comes under ""."""
    out: list[tuple[str, list[str]]] = [("", [])]
    for line in (markdown or "").splitlines():
        m = re.match(r"^#{1,6}\s+(.*)$", line)
        if m:
            out.append((m.group(1).strip(), []))
        else:
            out[-1][1].append(line)
    return [(h, "\n".join(body).strip()) for h, body in out if h or "\n".join(body).strip()]
