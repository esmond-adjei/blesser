"""What makes two records the same person or paper in the index.

alembic/versions/047_index_workspace.py keeps a frozen copy for its backfill.
"""

from __future__ import annotations

import re

from api.core.textnorm import canonical_openalex_id, normalize_text
from api.prospects import openalex

_DOI = re.compile(r"(10\.\d{4,9}/\S+)", re.IGNORECASE)
_OPENALEX_WORK = re.compile(r"openalex\.org/(W\d+)", re.IGNORECASE)


def person_key(name: str | None) -> str:
    """'Prof. Ada Lovelace, PhD' and 'ada lovelace' -> 'ada lovelace'."""
    return normalize_text(openalex.clean_person_name(name or "") or name)


def openalex_author(value: str | None) -> str | None:
    return canonical_openalex_id(value) or None


def doi_of(value: str | None) -> str | None:
    """The DOI in a DOI, a doi.org link or a publisher URL, lower case."""
    match = _DOI.search(value or "")
    return match.group(1).rstrip(".,;)").lower() if match else None


def work_key(
    *,
    title: str,
    year: int | None = None,
    doi: str | None = None,
    url: str | None = None,
    openalex_id: str | None = None,
) -> str:
    """DOI first, then the OpenAlex work id, then title and year."""
    found = doi_of(doi) or doi_of(url)
    if found:
        return f"doi:{found}"
    work = (openalex_id or "").rstrip("/").rsplit("/", 1)[-1].upper()
    if not work.startswith("W"):
        match = _OPENALEX_WORK.search(url or "")
        work = match.group(1).upper() if match else ""
    if work:
        return f"openalex:{work}"
    return f"title:{normalize_text(title)}|{year or ''}"
