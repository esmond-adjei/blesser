"""Grounding for save_professor_record: what gets stored comes from tool
results this task received, not from the model's restatement.

At save time:

- `openalex_id` must be one find_openalex_author returned and whose works
  were fetched, at the programme's school (`verified_by: faculty_page`
  skips the institution check);
- every cited paper must be one of those works; stored fields come from
  the source, not the model;
- `similarity_score` must be one score_alignment computed this task, and
  the tool's value is stored.

Authors from other sources (sources.py) carry a prefixed id, are grounded
the same way, and store their profile link instead of an OpenAlex id.
"""

from __future__ import annotations

from api.core.textnorm import canonical_openalex_id, normalize_text

#: Models round restated scores; the stored value is always the tool's own.
SCORE_TOLERANCE = 0.05
#: Share of a scored text's words that must appear in one fetched work.
TEXT_CONTAINMENT = 0.9

_STOP = {
    "the",
    "of",
    "and",
    "at",
    "in",
    "for",
    "de",
    "university",
    "universitat",
    "universite",
    "universidad",
    "universita",
    "institute",
    "college",
    "school",
}


def _norm(text: str | None) -> str:
    return normalize_text(text)


#: Author ids from sources other than OpenAlex carry one of these prefixes.
SOURCE_PREFIXES = ("dblp", "nih", "nsf", "orcid")


def is_source_id(value: str | None) -> bool:
    head, sep, _ = (value or "").strip().partition(":")
    return bool(sep) and head.lower() in SOURCE_PREFIXES


def author_key(value: str | None) -> str:
    """OpenAlex ids canonical ("A123"), other sources as "<source>:<id>"."""
    raw = (value or "").strip()
    if is_source_id(raw):
        head, _, rest = raw.partition(":")
        return f"{head.lower()}:{rest.strip()}"
    return canonical_openalex_id(raw)


def record_author_candidates(ctx, candidates: list[dict]) -> None:
    store = _store(ctx, "author_candidates", dict)
    for c in candidates or []:
        if isinstance(c, dict) and c.get("openalex_id"):
            store[author_key(str(c["openalex_id"]))] = c


def record_works(ctx, openalex_id: str, works: list[dict]) -> None:
    _store(ctx, "works_by_author", dict)[author_key(str(openalex_id))] = [
        w for w in works or [] if isinstance(w, dict) and w.get("title")
    ]


def works_for(ctx, openalex_id: str) -> list[dict]:
    store = getattr(ctx, "works_by_author", None) or {}
    return store.get(author_key(openalex_id)) or []


#: Why OpenAlex couldn't confirm a professor; NO_WORKS is stored as "no_works:<id>".
UNAVAILABLE, NOT_FOUND, NO_WORKS = "unavailable", "not_found", "no_works"


def record_openalex_outcome(ctx, outcome: str, openalex_id: str | None = None) -> None:
    key = f"{outcome}:{author_key(openalex_id)}" if openalex_id else outcome
    _store(ctx, "openalex_outcomes", set).add(key)


def unverified_save_error(ctx, tool_input: dict) -> str | None:
    """None when a professor may be saved unverified (no papers, no score), else why not."""
    if not (tool_input.get("rationale") or "").strip():
        return "An unverified save still needs a rationale: say what you checked and why OpenAlex couldn't confirm them."
    outcomes = getattr(ctx, "openalex_outcomes", None) or set()
    candidates = getattr(ctx, "author_candidates", None) or {}
    openalex_id = author_key(str(tool_input.get("openalex_id") or ""))
    if UNAVAILABLE in outcomes:
        return None
    if openalex_id and f"{NO_WORKS}:{openalex_id}" in outcomes and openalex_id in candidates:
        return None
    if NOT_FOUND in outcomes and not candidates:
        return None
    return (
        "unverified is only for professors OpenAlex can't confirm: it was "
        "unavailable, found nobody by this name, or lists no works for them. "
        "Here it returned candidates: save the one at the programme's school "
        "the normal way, or call confirm_no_match."
    )


def record_score(ctx, abstracts: list[str], result: dict) -> None:
    score = result.get("score") if isinstance(result, dict) else None
    if isinstance(score, (int, float)):
        _store(ctx, "alignment_scores", list).append(
            {"score": float(score), "texts": {_norm(a) for a in abstracts if a}}
        )


#: Providers rebuild messages from known fields, so this never reaches the model.
CHECKPOINT_KEY = "_grounding"


def snapshot(ctx) -> dict | None:
    """What the research tools recorded on `ctx`, JSON-safe."""
    candidates = getattr(ctx, "author_candidates", None) or {}
    works = getattr(ctx, "works_by_author", None) or {}
    scores = getattr(ctx, "alignment_scores", None) or []
    outcomes = getattr(ctx, "openalex_outcomes", None) or set()
    if not (candidates or works or scores or outcomes):
        return None
    return {
        "author_candidates": candidates,
        "works_by_author": works,
        "openalex_outcomes": sorted(outcomes),
        "alignment_scores": [
            {"score": s["score"], "texts": sorted(s["texts"])} for s in scores
        ],
    }


def attach_to_checkpoint(ctx, messages: list[dict]) -> list[dict]:
    """Snapshot on the last message: compacted history drops the tool payloads
    a resumed attempt needs to save."""
    state = snapshot(ctx)
    if state is None or not messages:
        return messages
    return [*messages[:-1], {**messages[-1], CHECKPOINT_KEY: state}]


def restore_from_checkpoint(ctx, messages: list[dict]) -> list[dict]:
    """Load the latest snapshot onto `ctx`; return the messages without it."""
    state = None
    cleaned = []
    for m in messages:
        if CHECKPOINT_KEY in m:
            state = m[CHECKPOINT_KEY]
            m = {k: v for k, v in m.items() if k != CHECKPOINT_KEY}
        cleaned.append(m)
    if isinstance(state, dict):
        try:
            # Keys canonicalised: older snapshots used the full-URL form.
            _store(ctx, "author_candidates", dict).update(
                {
                    author_key(k): v
                    for k, v in (state.get("author_candidates") or {}).items()
                }
            )
            _store(ctx, "works_by_author", dict).update(
                {
                    author_key(k): v
                    for k, v in (state.get("works_by_author") or {}).items()
                }
            )
            _store(ctx, "openalex_outcomes", set).update(state.get("openalex_outcomes") or [])
            _store(ctx, "alignment_scores", list).extend(
                {"score": float(s["score"]), "texts": set(s.get("texts") or [])}
                for s in state.get("alignment_scores") or []
            )
        except AttributeError:  # frozen test doubles
            pass
    return cleaned


def _store(ctx, name: str, factory):
    value = getattr(ctx, name, None)
    if value is None:
        value = factory()
        setattr(ctx, name, value)
    return value


_ACRONYM_SKIP = {
    "of",
    "the",
    "and",
    "de",
    "at",
    "for",
    "in",
    "la",
    "le",
    "di",
    "du",
    "des",
}


def _acronym(name: str) -> str:
    words = [w for w in _norm(name).split() if w not in _ACRONYM_SKIP]
    return "".join(w[0] for w in words) if len(words) >= 2 else ""


def _strong_name_match(a: str, b: str) -> bool:
    """Same institution by name alone: equal, or one is the other's
    acronym ("MIT", "UCL", "EPFL", "KNUST")."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    for short, full in ((na, b), (nb, a)):
        if " " not in short and 2 <= len(short) <= 6 and short == _acronym(full):
            return True
    return False


def _token_overlap(a: str, b: str) -> bool:
    ta = {t for t in _norm(a).split() if t not in _STOP and len(t) > 1}
    tb = {t for t in _norm(b).split() if t not in _STOP and len(t) > 1}
    if not ta or not tb:
        return _norm(a) == _norm(b)
    return bool(ta & tb)


def _institution_matches(
    candidate: dict | str | None,
    school: str | None,
    school_id: str | None = None,
    school_names: list[str] | tuple[str, ...] = (),
) -> bool:
    """With ids on both sides (lineage included, so a teaching hospital counts
    for its university): same id or a strong name match. Without ids: names,
    leniently, borderline cases left to review. No data at all: no refusal."""
    if isinstance(candidate, str) or candidate is None:
        candidate = {"institution": candidate}
    names = [n for n in candidate.get("institutions") or [] if n]
    if not names and candidate.get("institution"):
        names = [candidate["institution"]]
    school_all = [n for n in [school, *school_names] if n]
    if not names or not school_all:
        return True  # nothing to compare against; don't refuse on missing data
    ids = {str(i).upper() for i in candidate.get("institution_ids") or []}
    if school_id and ids:
        if school_id.upper() in ids:
            return True
        return any(_strong_name_match(n, s) for n in names for s in school_all)
    return any(
        _strong_name_match(n, s) or _token_overlap(n, s)
        for n in names
        for s in school_all
    )


def at_school(
    candidate: dict,
    school: str | None,
    school_id: str | None = None,
    school_names: list[str] | tuple[str, ...] = (),
) -> bool:
    """Faculty-page and other-source candidates were already placed at the school."""
    if candidate.get("verified_by"):
        return True
    return _institution_matches(candidate, school, school_id, school_names)


def _find_work(works: list[dict], title: str) -> dict | None:
    """A shortened title matches; a longer one only if the stored title is most
    of it, so "An Introduction to Diffusion Models" can't borrow "Introduction"."""
    want = _norm(title)
    if not want:
        return None
    for w in works:
        have = _norm(w.get("title"))
        if not have:
            continue
        if have == want:
            return w
        if len(want) >= 20 and want in have:
            return w
        if len(have) >= 20 and have in want and len(have) >= 0.6 * len(want):
            return w
    return None


def _from_fetched(text: str, docs: list[set[str]]) -> bool:
    """Nearly all words must appear in one work's title and abstract."""
    words = set(text.split())
    if not words:
        return False
    return any(len(words & doc) >= TEXT_CONTAINMENT * len(words) for doc in docs)


def ground_professor_save(
    tool_input: dict,
    ctx,
    school_name: str | None,
    school_id: str | None = None,
    school_names: list[str] | tuple[str, ...] = (),
) -> tuple[str | None, dict]:
    """(error, grounded_input). On success the returned input carries the
    OpenAlex papers and the tool-computed score in place of the model's."""
    openalex_id = author_key(str(tool_input.get("openalex_id") or ""))
    candidates = getattr(ctx, "author_candidates", None) or {}
    works_by_author = getattr(ctx, "works_by_author", None) or {}
    if not openalex_id or openalex_id not in candidates:
        return (
            (
                "openalex_id must be one find_openalex_author returned in this task. "
                "Disambiguate the professor first, or call confirm_no_match."
            ),
            tool_input,
        )
    candidate = candidates[openalex_id]
    institution = candidate.get("institution")
    if not at_school(candidate, school_name, school_id, school_names):
        return (
            (
                f"OpenAlex places this author at {institution!r}, not {school_name!r}. "
                "Pick the candidate at the programme's school, or call confirm_no_match."
            ),
            tool_input,
        )
    if openalex_id not in works_by_author:
        return (
            (
                "Fetch this author's works with get_author_works before saving; "
                "papers are stored from that result, not from your summary."
            ),
            tool_input,
        )

    works = works_by_author[openalex_id]
    papers: list[dict] = []
    unknown: list[str] = []
    for p in tool_input.get("papers") or []:
        title = p.get("title") if isinstance(p, dict) else None
        work = _find_work(works, title or "")
        if work is None:
            unknown.append(title or "(untitled)")
        elif work not in papers:
            papers.append(work)
    if unknown:
        return (
            (
                "These papers were not returned by get_author_works for this author: "
                f"{unknown}. Cite only fetched works."
            ),
            tool_input,
        )
    if not papers:
        return ("Cite at least one paper returned by get_author_works.", tool_input)

    claimed = tool_input.get("similarity_score")
    if not isinstance(claimed, (int, float)) or not 0.0 <= float(claimed) <= 1.0:
        return (
            "similarity_score must be the 0-1 value score_alignment returned.",
            tool_input,
        )
    docs = [
        set(_norm(f"{w.get('title') or ''} {w.get('abstract') or ''}").split())
        for w in works
    ]
    matches = [
        s["score"]
        for s in getattr(ctx, "alignment_scores", None) or []
        if abs(s["score"] - float(claimed)) <= SCORE_TOLERANCE
        and s["texts"]
        and all(_from_fetched(t, docs) for t in s["texts"])
    ]
    if not matches:
        return (
            (
                "similarity_score must come from score_alignment run on this author's "
                "fetched works in this task; never estimate it. Call score_alignment "
                "with the abstracts get_author_works returned for this author, using "
                "the title for any work without an abstract, then save with the "
                "score it returns."
            ),
            tool_input,
        )
    score = min(matches, key=lambda s: abs(s - float(claimed)))

    grounded = dict(tool_input)
    # OpenAlex's own id form, so dedup compares like with like.
    grounded["openalex_id"] = None if is_source_id(openalex_id) else candidate["openalex_id"]
    if candidate.get("links"):
        grounded["socials"] = [*(tool_input.get("socials") or []), *candidate["links"]]
    if candidate.get("save_note") and isinstance(tool_input.get("rationale"), str):
        grounded["rationale"] = f"{tool_input['rationale'].rstrip()} ({candidate['save_note']})"
    grounded["papers"] = [
        {
            "title": w.get("title"),
            "abstract": w.get("abstract"),
            "year": w.get("year"),
            "url": w.get("url"),
            "citations": w.get("citations"),
            "publication_type": w.get("publication_type"),
            "coauthors": w.get("coauthors"),
        }
        for w in papers
    ]
    grounded["similarity_score"] = score
    return None, grounded
