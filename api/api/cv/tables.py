"""GFM pipe tables in document Markdown: the syntax the editor writes
(webapp editor/tableSyntax.ts), read for the exports and plain text, and
written for tables in an uploaded Word file.

    | Degree | Year |
    | ------ | ---: |
    | BSc    | 2024 |

A table is a header row, a delimiter row of dashes (colons set a
column's alignment), then body rows; outer pipes are optional and `\\|`
is a literal pipe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_DELIMITER_CELL = re.compile(r"^\s*:?-+:?\s*$")


@dataclass
class Table:
    header: list[str]
    align: list[str | None]
    rows: list[list[str]] = field(default_factory=list)


def split_row(line: str) -> list[str]:
    """A row's cells, trimmed: split on unescaped pipes, outer pipes optional."""
    cells: list[str] = []
    cell = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and line[i + 1 : i + 2] == "|":
            cell += "\\|"
            i += 2
            continue
        if ch == "|":
            cells.append(cell)
            cell = ""
        else:
            cell += ch
        i += 1
    cells.append(cell)
    if re.match(r"^\s*\|", line):
        cells.pop(0)
    if re.search(r"\|\s*$", line.replace("\\|", "")):
        cells.pop()
    return [c.strip() for c in cells]


def is_delimiter_row(line: str) -> bool:
    cells = split_row(line)
    return bool(cells) and "-" in line and all(_DELIMITER_CELL.match(c) for c in cells)


def starts_table(lines: list[str], i: int) -> bool:
    """Whether a table starts at lines[i]: a row with a pipe, then a
    delimiter row of as many cells."""
    if i + 1 >= len(lines) or "|" not in lines[i] or not is_delimiter_row(lines[i + 1]):
        return False
    return len(split_row(lines[i])) == len(split_row(lines[i + 1]))


def _align(cell: str) -> str | None:
    c = cell.strip()
    left, right = c.startswith(":"), c.endswith(":")
    return "center" if left and right else "right" if right else "left" if left else None


def read_table(lines: list[str], i: int) -> tuple[Table, int]:
    """The table starting at lines[i] (see starts_table), and the index of
    the first line after it. Rows end at a blank line or one with no pipe."""
    header = split_row(lines[i])
    width = len(header)
    align = [_align(c) for c in split_row(lines[i + 1])]
    table = Table(header=header, align=(align + [None] * width)[:width])
    j = i + 2
    while j < len(lines) and lines[j].strip() and "|" in lines[j]:
        cells = split_row(lines[j])
        table.rows.append((cells + [""] * width)[:width])
        j += 1
    return table, j


def unescape(cell: str) -> str:
    return cell.replace("\\|", "|")


def escape(text: str) -> str:
    """Text for one cell: pipes escaped, line breaks as spaces."""
    return re.sub(r"\s*\n\s*", " ", text).replace("|", "\\|").strip()


def write_table(rows: list[list[str]]) -> str:
    """Rows of cell text (the first is the header) as a lined-up table."""
    width = max((len(r) for r in rows), default=0)
    if not width:
        return ""
    grid = [[escape(c) for c in (r + [""] * width)[:width]] for r in rows]
    widths = [max(3, *(len(r[c]) for r in grid)) for c in range(width)]

    def line(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[k]) for k, c in enumerate(cells)) + " |"

    out = [line(grid[0]), "| " + " | ".join("-" * w for w in widths) + " |"]
    out += [line(r) for r in grid[1:]]
    return "\n".join(out)
