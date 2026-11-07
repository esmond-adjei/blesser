"""Deadline text to a date, only when the text is unambiguous.

Parses ISO dates and forms naming one calendar date without guessing ("15
December 2026", "Dec 15, 2026", d/m/y with day > 12). Anything else stays NULL.
"""

import re
from datetime import date

_MONTHS = {
    name: i + 1
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ]
    )
    for name in names
}
_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_DMY_NUMERIC = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)\.?,?\s+(\d{4})$")
_MONTH_DAY_YEAR = re.compile(r"^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$")


def _make(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_deadline(text: str | None) -> date | None:
    raw = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not raw:
        return None
    if m := _ISO.match(raw):
        return _make(int(m[1]), int(m[2]), int(m[3]))
    if m := _DMY_NUMERIC.match(raw):
        first, second, year = int(m[1]), int(m[2]), int(m[3])
        if first > 12 >= second:
            return _make(year, second, first)
        if second > 12 >= first:
            return _make(year, first, second)
        return None  # 03/04/2026: March or April, can't tell
    if m := _DAY_MONTH_YEAR.match(raw):
        month = _MONTHS.get(m[2])
        return _make(int(m[3]), month, int(m[1])) if month else None
    if m := _MONTH_DAY_YEAR.match(raw):
        month = _MONTHS.get(m[1])
        return _make(int(m[3]), month, int(m[2])) if month else None
    return None
