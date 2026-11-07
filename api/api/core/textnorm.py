"""One text normaliser for every model-text vs source-text check, so they agree.

Strips markup, transliterates accents (not drops), and turns punctuation into
spaces so hyphenation variants compare equal.
"""

from __future__ import annotations

import html
import re
import unicodedata

_TAG = re.compile(r"<[^>]{0,200}>")
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    plain = _TAG.sub("", html.unescape(text))
    folded = unicodedata.normalize("NFKD", plain)
    ascii_only = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return _NON_WORD.sub(" ", ascii_only.lower()).strip()


def canonical_openalex_id(value: str | None) -> str:
    """ "https://openalex.org/A123", "openalex.org/a123" and "A123" -> "A123"."""
    raw = (value or "").strip().rstrip("/")
    return raw.rsplit("/", 1)[-1].upper()
