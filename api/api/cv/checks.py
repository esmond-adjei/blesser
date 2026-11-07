"""Read-only consistency checks for documents: hints the student may ignore."""

from __future__ import annotations

import difflib
import re
from datetime import UTC, datetime

from api.cv.markdown import to_plain_text

# Must match the editor's wordCount (webapp documentText.ts).
_HAS_WORD = re.compile(r"[A-Za-z0-9_]")


def word_count(markdown: str) -> int:
    return sum(1 for w in to_plain_text(markdown or "").split() if _HAS_WORD.search(w))


_PLACEHOLDER = re.compile(
    r"\bTODO\b|\bTBD\b|\bTKTK\b|\bXXX+\b|(?i:lorem ipsum)"
    # A bracket left to fill ([insert …], [X%]); a link's label is followed by "(".
    r"|\[(?i:insert|add|your|name|professor|prof\.?|university|school|program|lab|company|date|year)\b[^\]\n]*\](?!\()"
    r"|\[[XN](?:%| [^\]\n]*)?\](?!\()"
)


def _placeholders(text: str) -> list[dict]:
    out = []
    for n, line in enumerate(text.splitlines()):
        for m in _PLACEHOLDER.finditer(line):
            out.append(
                {
                    "kind": "placeholder",
                    "message": f"“{m.group(0)}” looks like a placeholder left to fill.",
                    "quote": m.group(0),
                    "line": n,
                }
            )
    return out


_MONTHS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}  # fmt: skip
# Capitalized only because they start a sentence or a title; never part of a name.
_LEADING = {
    "a", "an", "the", "at", "in", "on", "as", "i", "my", "our", "we", "during", "after",
    "before", "while", "when", "since", "from", "with", "for", "and", "this", "that",
    "there", "then", "professor", "prof", "dr", "mr", "ms", "mrs",
}  # fmt: skip
_CONNECTORS = {"of", "for", "and", "de", "&"}
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9&'’-]*|&")
_YEAR_RANGE = re.compile(
    r"\b((?:19|20)\d\d)\s*(?:[-–—]|to)\s*((?:19|20)\d\d|[Pp]resent|[Nn]ow|[Cc]urrent)\b"
)
_YEAR = re.compile(r"\b(?:19|20)\d\d\b")
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")


def _names(text: str) -> list[str]:
    """Capitalized phrases of two or more words: "Soft Robotics Lab",
    "University of Ghana". Leading sentence words and months break them."""
    out: list[str] = []
    run: list[str] = []

    def close():
        while run and (run[-1].lower() in _LEADING | _CONNECTORS or run[-1] == "the"):
            run.pop()
        while run and run[0].lower() in _LEADING | _CONNECTORS:
            run.pop(0)
        if len(run) >= 2:
            out.append(" ".join(run))
        run.clear()

    end = 0
    for m in _TOKEN.finditer(text):
        word = m.group(0)
        if run and text[end : m.start()].strip():
            close()  # punctuation between words ends a name
        end = m.end()
        if word.lower() in _MONTHS:
            close()
        elif word[0].isupper() or (
            run and (word.lower() in _CONNECTORS or (word == "the" and run[-1] == "of"))
        ):
            run.append(word)
        else:
            close()
    close()
    return out


def _years(text: str) -> set[int]:
    years: set[int] = set()
    for m in _YEAR_RANGE.finditer(text):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2)[0].isdigit() else datetime.now(UTC).year
        if start <= end <= start + 40:
            years.update(range(start, end + 1))
    years.update(int(y) for y in _YEAR.findall(text))
    return years


def _cv_facts(cv_texts: list[str]) -> dict[str, set[int]]:
    """Each name in the CVs with the years on its line (or bullet)."""
    facts: dict[str, set[int]] = {}
    for text in cv_texts:
        for line in (text or "").splitlines():
            years = _years(line)
            for name in _names(line):
                facts.setdefault(name.lower(), set()).update(years)
    return facts


def _span(years: set[int]) -> str:
    lo, hi = min(years), max(years)
    return str(lo) if lo == hi else f"{lo}–{hi}"


def _against_cv(text: str, cv_texts: list[str]) -> list[dict]:
    facts = _cv_facts(cv_texts)
    if not facts:
        return []
    out: list[dict] = []
    seen: set[tuple] = set()
    known = {k: k for k in facts}
    for n, line in enumerate(text.splitlines()):
        for sm in _SENTENCE.finditer(line):
            sentence = sm.group(0).strip()
            if not sentence:
                continue
            years = _years(sentence)
            for name in _names(sentence):
                key = name.lower()
                if key in facts:
                    cv_years = facts[key]
                    if (
                        years
                        and cv_years
                        and not years & cv_years
                        and (key, "date") not in seen
                    ):
                        seen.add((key, "date"))
                        out.append(
                            {
                                "kind": "date_mismatch",
                                "message": f"{name}: this says {_span(years)}, your CV says {_span(cv_years)}.",
                                "quote": sentence,
                                "line": n,
                            }
                        )
                    continue
                close = difflib.get_close_matches(key, list(known), n=1, cutoff=0.88)
                if (
                    close
                    and len(close[0].split()) == len(key.split())
                    and (key, "name") not in seen
                ):
                    seen.add((key, "name"))
                    cv_name = _original(cv_texts, close[0])
                    out.append(
                        {
                            "kind": "name_mismatch",
                            "message": f"“{name}” is spelled “{cv_name}” in your CV.",
                            "quote": name,
                            "line": n,
                        }
                    )
    return out


def _original(cv_texts: list[str], lowered: str) -> str:
    for text in cv_texts:
        for name in _names(text or ""):
            if name.lower() == lowered:
                return name
    return lowered


_FACULTY = re.compile(
    r"\b(?:Professor|Prof\.?|Dr\.?)\s+((?:[A-Z][A-Za-z'’-]+\.?)(?:\s+[A-Z][A-Za-z'’-]+\.?){0,2})"
)


def _norm(name: str) -> list[str]:
    return [w.strip(".").lower() for w in name.split() if w.strip(".")]


def _is_target(name: str, targets: list[str]) -> bool:
    words = _norm(name)
    if not words:
        return True
    for t in targets:
        tw = _norm(t)
        if not tw or tw[-1] != words[-1]:
            continue
        # "Professor Lovelace" matches "Ada Lovelace"; a given first name must
        # agree (an initial is enough).
        if len(words) == 1 or tw[0][0] == words[0][0]:
            return True
    return False


def _faculty(text: str, targets: list[str]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for n, line in enumerate(text.splitlines()):
        for m in _FACULTY.finditer(line):
            name = m.group(1).rstrip(".")
            if name.lower() in seen or _is_target(name, targets):
                continue
            seen.add(name.lower())
            out.append(
                {
                    "kind": "unknown_faculty",
                    "message": f"{m.group(0).rstrip('.')} isn't among your targets. Check the name, or add them.",
                    "quote": m.group(0).rstrip("."),
                    "line": n,
                }
            )
    return out


#: Kinds that state facts about the student and name faculty.
STATEMENT_KINDS = {"sop", "diversity_statement", "research_proposal", "interest"}


def run_checks(
    text: str,
    kind: str,
    cv_texts: list[str] | None = None,
    targets: list[str] | None = None,
) -> list[dict]:
    """Findings for `text`, in document order. A CV is checked for
    placeholders only; a statement also against the CVs and the targets."""
    findings = _placeholders(text or "")
    if kind in STATEMENT_KINDS:
        findings += _against_cv(text or "", cv_texts or [])
        findings += _faculty(text or "", targets or [])
    return sorted(findings, key=lambda f: f["line"])
