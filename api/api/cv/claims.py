"""The "no new facts" check for CV suggestions: every content word a
suggestion adds must already appear in the base CV. A lexical tripwire,
not a prover."""

import re

_CLAIM_STOPWORDS = frozenset(
    [
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
        "with", "as", "at", "by", "from", "that", "this", "it", "its",
        "is", "are", "was", "were", "be", "been", "have", "has", "had",
        "will", "would", "can", "could", "should", "may",
        "not", "no", "new", "more", "most", "my", "our", "you", "your",
        "we", "they", "their", "his", "her",
        "per", "via", "including", "led", "built", "using", "use", "used",
        "within", "across", "both", "between", "strong", "proven", "track",
        "record", "experience", "skilled", "passionate", "motivated",
        "detail", "oriented", "team", "player", "proficient", "experienced",
    ]
)

_CLAIM_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")


def claim_tokens(text: str) -> set[str]:
    """Content-bearing tokens: drop stopwords and bare short words, but
    always keep anything with a digit (years, counts, versions matter)."""
    out = set()
    for w in _CLAIM_TOKEN_RE.findall((text or "").lower()):
        if w in _CLAIM_STOPWORDS:
            continue
        if len(w) > 2 or any(ch.isdigit() for ch in w):
            out.add(w)
    return out


def check_new_terms(base_markdown: str, replace: str) -> dict:
    """{"passed": bool, "new_terms": [...]}: the replacement's content words
    the base CV never mentions (up to 12, sorted)."""
    novel = sorted(claim_tokens(replace) - claim_tokens(base_markdown))
    return {"passed": not novel, "new_terms": novel[:12]}
