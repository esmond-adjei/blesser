"""Gradis citations: the server, not the model, decides what can be cited.

Each tool result registers its records and pages under a key (s1, s2, ...)
stable for the conversation; a finished reply keeps only issued keys.
Sources ride on tool events in the turn log, so the registry is rebuilt
from the stored transcript.
"""

import re
from urllib.parse import urlparse

#: Snippets are a preview, not the record.
_SNIPPET_CHARS = 240
#: The most sources one tool result registers; long lists cite the top.
_PER_RESULT = 12

#: A citation as the model writes it: [s3], or a list like [s1, s3]. Code
#: spans and fences are matched first so a citation-looking string inside
#: code is left alone.
_CITE = re.compile(r"(```[\s\S]*?```|`[^`\n]*`)|([ \t]*)\[(s\d+(?:\s*,\s*s\d+)*)\]")


def _clip(text: object, limit: int = _SNIPPET_CHARS) -> str | None:
    if not text:
        return None
    flat = " ".join(str(text).split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rsplit(" ", 1)[0] + "…"


def _join(*parts: object) -> str | None:
    text = " · ".join(str(p) for p in parts if p)
    return text or None


def _entity(kind: str, id_: object, title: object, href: str | None, **extra) -> dict | None:
    if not id_ or not title:
        return None
    out = {"kind": kind, "id": str(id_), "title": str(title), "href": href}
    out.update({k: v for k, v in extra.items() if v not in (None, "")})
    return out


def _run(d: dict) -> dict | None:
    return _entity(
        "run",
        d.get("id"),
        _join(d.get("field"), d.get("region")) or "Research run",
        f"/runs/{d.get('id')}",
        subtitle=d.get("status"),
        snippet=_clip(d.get("interest")),
    )


def _candidate(d: dict) -> dict | None:
    return _entity(
        "candidate",
        d.get("id"),
        d.get("professor_name") or d.get("professor"),
        f"/dossier/{d.get('id')}",
        subtitle=_join(d.get("school_name") or d.get("school"), d.get("program_name")),
        snippet=_clip(d.get("rationale")),
        image_url=d.get("professor_photo_url"),
        score=d.get("similarity_score"),
    )


def _professor(d: dict) -> dict | None:
    candidate_id = d.get("candidate_id")
    return _entity(
        "professor",
        d.get("id"),
        d.get("name"),
        f"/dossier/{candidate_id}" if candidate_id else f"/professors/{d.get('id')}",
        subtitle=_join(
            d.get("lab_name") or d.get("lab"),
            d.get("school_name") or d.get("school"),
        ),
        snippet=_clip(d.get("bio")),
        image_url=d.get("photo_url"),
    )


def _program(d: dict) -> dict | None:
    if d.get("run_id"):
        href = f"/runs/{d['run_id']}/programmes/{d.get('id')}"
    elif d.get("school_id"):
        href = f"/schools/{d['school_id']}"
    else:
        href = None
    return _entity(
        "program",
        d.get("id"),
        d.get("name"),
        href,
        subtitle=d.get("school_name") or d.get("school"),
        image_url=d.get("school_image_url"),
    )


def _school(d: dict) -> dict | None:
    return _entity(
        "school", d.get("id"), d.get("name"), f"/schools/{d.get('id')}",
        subtitle=d.get("country"), image_url=d.get("image_url"),
    )


def _application(d: dict) -> dict | None:
    deadline = d.get("deadline")
    return _entity(
        "application",
        d.get("id"),
        d.get("school"),
        f"/applications/{d.get('id')}",
        subtitle=_join(d.get("program"), f"due {deadline}" if deadline else None),
        snippet=_clip(d.get("notes")),
        program=d.get("program"),
        image_url=d.get("school_image_url"),
    )


def _draft(d: dict) -> dict | None:
    return _entity(
        "draft",
        d.get("id"),
        d.get("subject") or "Email draft",
        f"/outbox/{d.get('id')}",
        subtitle=d.get("professor_name") or d.get("professor"),
    )


def _cv(d: dict) -> dict | None:
    document_id = d.get("document_id") or d.get("id")
    version_id = d.get("version_id")
    return _entity(
        "cv" if (d.get("kind") or "cv") == "cv" else "document",
        document_id,
        d.get("name") or d.get("title"),
        f"/documents/{document_id}" + (f"?version={version_id}" if version_id else ""),
        subtitle=d.get("tailored_for"),
    )


def _document(d: dict) -> dict | None:
    from api.cv.kinds import noun

    kind = noun(d.get("kind"))
    return _entity(
        "document", d.get("id"), d.get("title"), f"/documents/{d.get('id')}",
        subtitle=kind if kind.isupper() else kind.capitalize(),
    )


def _saved_paper(d: dict) -> dict | None:
    return _entity(
        "paper",
        d.get("id"),
        d.get("title"),
        f"/professors/{d.get('professor_id')}?paper={d.get('id')}",
        subtitle=_join(d.get("professor"), d.get("year")),
        snippet=d.get("abstract"),
        year=d.get("year"),
        url=d.get("url"),
    )


def _web(d: dict) -> dict | None:
    url = str(d.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    return {
        "kind": "web",
        "url": url,
        "title": str(d.get("title") or _host(url)),
        "subtitle": _host(url),
        **({"snippet": s} if (s := _clip(d.get("snippet"))) else {}),
    }


def _paper(d: dict) -> dict | None:
    if not d.get("title"):
        return None
    url = str(d.get("url") or "").strip()
    out = {
        "kind": "paper",
        "title": str(d["title"]),
        "url": url if url.startswith(("http://", "https://")) else None,
    }
    if d.get("venue"):
        out["venue"] = str(d["venue"])
    if d.get("year"):
        out["year"] = d["year"]
    if snippet := _clip(d.get("abstract")):
        out["snippet"] = snippet
    return out


def _author(d: dict) -> dict | None:
    openalex_id = str(d.get("openalex_id") or "")
    if not openalex_id or not d.get("display_name"):
        return None
    short = openalex_id.rsplit("/", 1)[-1]
    works = d.get("works_count")
    return {
        "kind": "author",
        "id": short,
        "title": str(d["display_name"]),
        "url": f"https://openalex.org/{short}",
        **({"subtitle": s} if (s := _join(d.get("institution"), f"{works} works" if works else None)) else {}),
    }


def _host(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.") or url


def _each(rows: object, build) -> list[dict]:
    if not isinstance(rows, list):
        return []
    return [s for r in rows[:_PER_RESULT] if isinstance(r, dict) and (s := build(r))]


def _fetch_page(result: dict, tool_input: dict) -> list[dict]:
    url = str(tool_input.get("url") or "").strip()
    text = str(result.get("text") or "").strip()
    # An unreadable page comes back as a bracketed note, not page text.
    if not url.startswith(("http://", "https://")) or not text or text.startswith("["):
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0][:120] if lines else _host(url)
    return [
        {
            "kind": "web",
            "url": url,
            "title": title,
            "subtitle": _host(url),
            **({"snippet": s} if (s := _clip(" ".join(lines[1:6]))) else {}),
        }
    ]


def search_sources(result: dict) -> list[dict]:
    """The app-wide search tool: hits per kind."""
    return [
        *_each(result.get("runs"), _run),
        *_each(result.get("schools"), _school),
        *_each(result.get("programs"), _program),
        *_each(result.get("professors"), _professor),
        *_each(result.get("candidates"), _candidate),
        *_each(result.get("applications"), _application),
        *_each(result.get("drafts"), _draft),
        *_each(result.get("documents"), _document),
        *_each(result.get("papers"), _saved_paper),
    ]


def _cv_documents(result: dict) -> list[dict]:
    return _each(
        result.get("documents"),
        lambda d: _cv({"id": d.get("id"), "title": d.get("title"), "kind": d.get("kind")}),
    )


#: Per tool: result (and input) -> raw sources. A tool not listed here
#: registers nothing.
_EXTRACTORS = {
    "list_runs": lambda r, _i: _each(r.get("runs"), _run),
    "get_run": lambda r, _i: [s] if (s := _run(r)) else [],
    "list_candidates": lambda r, _i: _each(r.get("candidates"), _candidate),
    "get_candidate": lambda r, _i: [s] if (s := _candidate(r)) else [],
    "list_applications": lambda r, _i: _each(r.get("applications"), _application),
    "get_application": lambda r, _i: [s] if (s := _application(r)) else [],
    "cv_get_application_context": lambda r, _i: [s] if (s := _application(r)) else [],
    "list_drafts": lambda r, _i: _each(r.get("drafts"), _draft),
    "list_candidate_drafts": lambda r, _i: _each(r.get("drafts"), _draft),
    "search_web": lambda r, _i: _each(r.get("results"), _web),
    "fetch_page": _fetch_page,
    "find_openalex_author": lambda r, _i: _each(r.get("candidates"), _author),
    "get_author_works": lambda r, _i: _each(r.get("works"), _paper),
    "cv_list_documents": lambda r, _i: _cv_documents(r),
    "cv_read": lambda r, _i: [s] if (s := _cv(r)) else [],
    "list_documents": lambda r, _i: _cv_documents(r),
    "read_document": lambda r, _i: [s] if (s := _cv(r)) else [],
    "search": lambda r, _i: search_sources(r),
    "list_schools": lambda r, _i: _each(r.get("schools"), _school),
    "get_school": lambda r, _i: [s] if (s := _school(r)) else [],
    "get_program": lambda r, _i: [s] if (s := _program(r)) else [],
    "get_professor": lambda r, _i: [s] if (s := _professor(r)) else [],
    "show_record": lambda r, _i: _shown(r),
}


#: The card builder for each kind show_record shows.
_SHOWN_KINDS = {
    "candidate": _candidate,
    "professor": _professor,
    "school": _school,
    "program": _program,
    "application": _application,
    "draft": _draft,
    "run": _run,
    "document": _document,
    "paper": _saved_paper,
}


def _shown(result: dict) -> list[dict]:
    build = _SHOWN_KINDS.get(result.get("kind"))
    # Older turns logged a single "record".
    records = result.get("records") or [result.get("record")]
    if build is None:
        return []
    return [s for r in records if isinstance(r, dict) and (s := build(r))]


def extract_sources(tool_name: str, result: object, tool_input: dict | None = None) -> list[dict]:
    """What one tool result can be cited as, without keys. Tolerant: an
    unknown tool, an error result or an odd shape registers nothing."""
    extractor = _EXTRACTORS.get(tool_name)
    if extractor is None or not isinstance(result, dict) or "error" in result:
        return []
    try:
        return extractor(result, tool_input or {})
    except Exception:  # noqa: BLE001 - a citation is never worth a failed turn
        return []


def _identity(source: dict) -> tuple:
    """Two sources are the same thing when they name the same record or
    page; a paper without a link is known by its title."""
    if source.get("url") and source.get("kind") in ("web", "paper", "author"):
        return (source["kind"], source["url"])
    if source.get("id"):
        return (source["kind"], source["id"])
    return (source.get("kind"), (source.get("title") or "").lower())


class SourceRegistry:
    """The conversation's citable sources by key, in the order issued."""

    def __init__(self) -> None:
        self.by_key: dict[str, dict] = {}
        self._keys: dict[tuple, str] = {}

    @classmethod
    def from_events(cls, events: list[dict]) -> "SourceRegistry":
        registry = cls()
        registry.absorb(events)
        return registry

    def absorb(self, events: list[dict]) -> None:
        """Take in the keys a stored turn log already issued."""
        for event in events:
            for source in event.get("sources") or []:
                key = source.get("key") if isinstance(source, dict) else None
                if key and key not in self.by_key:
                    self.by_key[key] = source
                    self._keys[_identity(source)] = key

    def _next_key(self) -> str:
        n = max((int(k[1:]) for k in self.by_key if k[1:].isdigit()), default=0)
        return f"s{n + 1}"

    def register(self, sources: list[dict]) -> list[dict]:
        """Key each source; one seen before keeps its key."""
        out = []
        for source in sources:
            identity = _identity(source)
            key = self._keys.get(identity)
            if key is None:
                key = self._next_key()
                self._keys[identity] = key
                self.by_key[key] = {"key": key, **source}
            if self.by_key[key] not in out:
                out.append(self.by_key[key])
        return out

    def cited(self, text: str) -> list[dict]:
        """The sources the text cites, in order of first citation."""
        seen: list[str] = []
        for key in cited_keys(text):
            if key in self.by_key and key not in seen:
                seen.append(key)
        return [self.by_key[k] for k in seen]


def cited_keys(text: str) -> list[str]:
    """Every key the text cites outside code, in order, with repeats."""
    keys = []
    for m in _CITE.finditer(text or ""):
        if m.group(3):
            keys.extend(k.strip() for k in m.group(3).split(","))
    return keys


def strip_unknown(text: str, known: set[str] | dict) -> tuple[str, list[str]]:
    """Drop citations of keys the server never issued, and write a list
    like [s1, s3] as [s1][s3]. Returns the text and the dropped keys."""
    dropped: list[str] = []

    def fix(m: re.Match) -> str:
        if not m.group(3):
            return m.group(0)
        keys = [k.strip() for k in m.group(3).split(",")]
        kept = [k for k in keys if k in known]
        dropped.extend(k for k in keys if k not in known)
        # A citation that goes entirely takes its leading space with it.
        return m.group(2) + "".join(f"[{k}]" for k in kept) if kept else ""

    return _CITE.sub(fix, text or ""), dropped


def sources_note(sources: list[dict]) -> str:
    """The keys the model may cite for one result, as it reads them."""
    if not sources:
        return ""
    lines = [f"[{s['key']}] {s['title']}" for s in sources]
    return "\n\nsources:\n" + "\n".join(lines)
