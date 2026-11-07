"""Gradis tool implementations. Reads return small LLM-friendly summaries;
writes reuse the feature owners' handlers, so budgets, dedup and the
never-send rule apply as they do for the worker."""

import re

from sqlalchemy import select

from api.agent.tools.context import ToolContext
from api.applications import service as application_service
from api.applications import tools as application_tools
from api.assistant import crud_tools
from api.candidates import scoring
from api.candidates import service as candidate_service
from api.core.config import settings
from api.cv import checks as cv_checks
from api.cv import kinds as cv_kinds
from api.cv import schemas as cv_schemas
from api.cv import service as cv_service
from api.outreach import service as outreach_service
from api.outreach import tools as outreach_tools
from api.prospects import openalex, web
from api.prospects import service as prospect_service
from api.prospects import tools as prospect_tools
from api.runs import models as run_models
from api.runs import service as run_service

_SUMMARY_LIMIT = 15
#: The most CV text one read returns; academic CVs run long.
_CV_TEXT_CHARS = 20000


def _summarize_run(d: dict) -> dict:
    return {
        "id": d["id"],
        "field": d.get("field"),
        "region": d.get("region"),
        "degree_level": d.get("degree_level"),
        "status": d.get("status"),
        "tasks": d.get("tasks"),
        "candidates": d.get("candidates"),
    }


async def _list_runs(tool_input: dict, session, user_id) -> dict:
    del tool_input
    runs = await run_service.list_runs(session, user_id)
    return {"runs": [_summarize_run(r) for r in runs[:_SUMMARY_LIMIT]]}


async def _get_run(tool_input: dict, session, user_id) -> dict:
    row = await run_service.get_run_or_404(session, tool_input["run_id"], user_id)
    return _summarize_run(await run_service.run_detail(session, row))


async def _list_candidates(tool_input: dict, session, user_id) -> dict:
    items, total = await candidate_service.list_candidates(
        session,
        user_id,
        tool_input["run_id"],
        status=tool_input.get("status"),
        limit=min(int(tool_input.get("limit", 10)), 20),
        offset=0,
        sort="score",
    )
    return {
        "total": total,
        "candidates": [
            {
                "id": c["id"],
                "professor_name": c["professor_name"],
                "school_name": c["school_name"],
                "program_name": c["program_name"],
                "similarity_score": c["similarity_score"],
                "rationale": c["rationale"],
                "status": c["status"],
                "draft_id": c["draft_id"],
                "draft_count": c.get("draft_count", 0),
            }
            for c in items
        ],
    }


async def _get_candidate(tool_input: dict, session, user_id) -> dict:
    d = await candidate_service.get_candidate_detail(
        session, user_id, tool_input["candidate_id"]
    )
    d["papers"] = [
        {"title": p["title"], "year": p.get("year")} for p in d.get("papers", [])[:10]
    ]
    if d.get("draft_body"):
        d["draft_body"] = d["draft_body"][:1500]
    return d


async def _list_programs(tool_input: dict, session, user_id) -> dict:
    tree = await prospect_service.list_programs_tree(
        session, user_id, tool_input["run_id"]
    )
    return {
        "schools": [
            {
                "name": s["name"],
                "country": s.get("country"),
                "programs": [
                    {"name": p["name"], "professors": p["professors"]}
                    for p in s.get("programs", [])
                ],
            }
            for s in tree[:_SUMMARY_LIMIT]
        ]
    }


async def _list_tasks(tool_input: dict, session, user_id) -> dict:
    status = tool_input.get("status")
    stmt = (
        select(
            run_models.ResearchTask.id,
            run_models.ResearchTask.task_type,
            run_models.ResearchTask.target_name,
            run_models.ResearchTask.status,
            run_models.ResearchTask.error,
        )
        .where(
            run_models.ResearchTask.run_id == tool_input["run_id"],
            run_models.ResearchTask.user_id == user_id,
        )
        .order_by(run_models.ResearchTask.created_at.desc())
        .limit(_SUMMARY_LIMIT)
    )
    if status and status != "all":
        stmt = stmt.where(
            run_models.ResearchTask.status == run_models.TaskStatus(status)
        )
    rows = (await session.execute(stmt)).all()
    return {
        "tasks": [
            {
                "id": r[0],
                "task_type": r[1],
                "target_name": r[2],
                "status": run_models.status_str(r[3]),
                "error": r[4],
            }
            for r in rows
        ]
    }


async def _list_applications(tool_input: dict, session, user_id) -> dict:
    del tool_input
    apps = await application_service.list_applications(session, user_id)
    return {
        "applications": [
            {
                "id": a["id"],
                "school": a["school"],
                "program": a["program"],
                "deadline": a.get("deadline"),
                "status": a.get("status"),
            }
            for a in apps[:_SUMMARY_LIMIT]
        ]
    }


async def _get_application(tool_input: dict, session, user_id) -> dict:
    app = await application_service.get_application_or_404(
        session, tool_input["application_id"], user_id
    )
    d = application_service.to_out(app)
    d["notes"] = (d.get("notes") or "")[:1500]
    return d


async def _list_drafts(tool_input: dict, session, user_id) -> dict:
    drafts = await outreach_service.list_drafts(session, user_id, tool_input["run_id"])
    return {
        "drafts": [
            {
                "id": d["id"],
                "professor_name": d.get("professor_name"),
                "subject": d.get("subject"),
            }
            for d in drafts[:_SUMMARY_LIMIT]
        ]
    }


async def _list_candidate_drafts(tool_input: dict, session, user_id) -> dict:
    drafts = await outreach_service.list_candidate_drafts(
        session, user_id, tool_input["candidate_id"]
    )
    return {
        "drafts": [
            {"id": d["id"], "subject": d.get("subject")}
            for d in drafts[:_SUMMARY_LIMIT]
        ]
    }


async def _search_web(tool_input: dict, session, user_id) -> dict:
    del session
    from api.billing import service as billing

    refusal = await billing.tool_call_refusal(
        user_id, "search", settings.search_provider
    )
    if refusal is not None:
        return {"error": refusal}
    return {"results": web.brief_results(await web.search_web(tool_input["query"]))}


async def _fetch_page(tool_input: dict, session, user_id) -> dict:
    del session, user_id
    return {
        "text": await web.fetch_page(
            tool_input["url"],
            max_chars=settings.fetch_max_chars,
            offset=tool_input.get("offset") or 0,
        )
    }


async def _find_openalex_author(tool_input: dict, session, user_id) -> dict:
    del session, user_id
    return {
        "candidates": await openalex.find_author(
            tool_input["name"], tool_input.get("institution_hint")
        )
    }


async def _get_author_works(tool_input: dict, session, user_id) -> dict:
    del session, user_id
    works = await openalex.get_recent_works(tool_input["openalex_id"])
    # Co-authors are saved with the papers; the model only needs how many.
    return {"works": [{**{k: v for k, v in w.items() if k != "coauthors"}, "coauthor_count": len(w.get("coauthors") or [])} for w in works]}


async def _score_alignment(tool_input: dict, session, user_id) -> dict:
    del session
    from api.billing import service as billing

    refusal = await billing.tool_call_refusal(
        user_id, "scoring", settings.embedding_provider, settings.embedding_model
    )
    if refusal is not None:
        return {"error": refusal}
    return scoring.embed_and_score(tool_input["interest_text"], tool_input["abstracts"])


async def _ctx_for_run(session, user_id, run_id: str) -> ToolContext:
    row = await run_service.get_run_or_404(session, run_id, user_id)
    # Chat writes are user-approved additions, not the agent's research
    # allowance.
    return ToolContext(session, row, metered=False)


async def _save_program(tool_input: dict, session, user_id) -> dict:
    ctx = await _ctx_for_run(session, user_id, tool_input.pop("run_id"))
    return await prospect_tools.handle_save_program(tool_input, ctx)


async def _save_application(tool_input: dict, session, user_id) -> dict:
    data = dict(tool_input)
    run_id = data.pop("run_id")
    ctx = await _ctx_for_run(session, user_id, run_id)
    return await application_tools.handle_save_application(data, ctx)


async def _save_email_draft(tool_input: dict, session, user_id) -> dict:
    candidate = await candidate_service.get_candidate_or_404(
        session, tool_input["candidate_id"], user_id
    )
    ctx = await _ctx_for_run(session, user_id, candidate.run_id)
    return await outreach_tools.handle_save_email_draft(tool_input, ctx)


async def _review_candidate(tool_input: dict, session, user_id) -> dict:
    return await candidate_service.review_candidate(
        session, user_id, tool_input["candidate_id"], bool(tool_input["approved"])
    )


async def _update_application(tool_input: dict, session, user_id) -> dict:
    data = dict(tool_input)
    application_id = data.pop("application_id")
    allowed = {
        "school",
        "program",
        "degree_type",
        "location",
        "link",
        "offer",
        "deadline",
        "status",
        "notes",
        "fee_waiver",
        "fee_waiver_notes",
    }
    patch = {k: v for k, v in data.items() if k in allowed}
    if not patch:
        return {"error": "No updatable fields given."}
    from api.applications import schemas as application_schemas

    return await application_service.update_application(
        session, user_id, application_id, application_schemas.ApplicationUpdate(**patch)
    )


async def _update_draft(tool_input: dict, session, user_id) -> dict:
    data = {
        k: tool_input[k] for k in ("subject", "body") if tool_input.get(k) is not None
    }
    if not data:
        return {"error": "Nothing to update: give subject and/or body."}
    return await outreach_service.update_draft(
        session, user_id, tool_input["draft_id"], data
    )


_KINDS = ("cv", "sop", "diversity_statement", "research_proposal", "interest", "note")


def _kind_error(doc, want: str | None) -> dict | None:
    """An error result when `doc` is not of the kind the caller asked for."""
    if want and (doc.kind or "cv") != want:
        return {
            "error": (
                f"That document is a {cv_kinds.noun(doc.kind)}, not a {cv_kinds.noun(want)}. "
                "Use read_document / suggest_changes with its kind."
            )
        }
    return None


async def _list_documents(tool_input: dict, session, user_id) -> dict:
    """The student's base documents (optionally of one kind or in one
    folder), each with its tailored versions, plus their folders."""
    kind = tool_input.get("kind") or None
    if kind and kind not in _KINDS:
        return {"error": f"Unknown kind {kind!r}; use one of {', '.join(_KINDS)}."}
    docs = await cv_service.list_documents(
        session, user_id, kind, tool_input.get("folder_id") or None
    )
    folders = await cv_service.list_folders(session, user_id)
    names = {f["id"]: f["name"] for f in folders}
    out = []
    for d in docs[:_SUMMARY_LIMIT]:
        out.append(
            {
                "id": d["id"],
                "title": d["title"],
                "kind": d["kind"],
                "folder": names.get(d.get("folder_id")),
                "updated_at": d.get("updated_at"),
                "versions": [
                    {
                        "id": v["id"],
                        "name": v["name"],
                        "candidate_id": v.get("candidate_id"),
                        "application_id": v.get("application_id"),
                        "tailored_for": v.get("target_label"),
                    }
                    for v in d["versions"][:_SUMMARY_LIMIT]
                ],
            }
        )
    return {
        "documents": out,
        "folders": [{"id": f["id"], "name": f["name"]} for f in folders],
        "note": "Outreach emails aren't documents: they're drafts in the Outbox (list_drafts).",
    }


async def _read_document(tool_input: dict, session, user_id, want: str | None = None) -> dict:
    """A document's Markdown: the base text, or one tailored version."""
    doc = await cv_service.get_document_or_404(session, tool_input["document_id"], user_id)
    if (err := _kind_error(doc, want or tool_input.get("kind"))) is not None:
        return err
    version_id = tool_input.get("version_id")
    if version_id:
        v = await cv_service.get_version(session, user_id, version_id)
        if v["document_id"] != doc.id:
            return {"error": "That version belongs to another document."}
        text, name = v["markdown"], v["name"]
        extra = {
            "version_id": v["id"],
            "tailored_for": v.get("target_label"),
            "candidate_id": v.get("candidate_id"),
            "application_id": v.get("application_id"),
        }
    else:
        text, name, extra = doc.markdown or "", doc.title, {}
    target = await cv_service.get_version_or_404(session, version_id, user_id) if version_id else doc
    word_limit, page_limit = cv_service.effective_limits(doc, target)
    if word_limit or page_limit:
        extra["limits"] = {
            "word_limit": word_limit,
            "page_limit": page_limit,
            "words": cv_checks.word_count(text),
        }
    checks = await cv_service.document_checks(session, user_id, doc.id, version_id)
    if checks["findings"]:
        # Read-only hints to raise with the student; never fixed silently.
        extra["checks"] = [
            {k: f[k] for k in ("kind", "message", "quote")} for f in checks["findings"][:20]
        ]
    return {
        "document_id": doc.id,
        "kind": doc.kind or "cv",
        "name": name,
        **extra,
        "truncated": len(text) > _CV_TEXT_CHARS,
        "markdown": text[:_CV_TEXT_CHARS],
    }


async def _suggest_changes(tool_input: dict, session, user_id, want: str | None = None) -> dict:
    """Store suggested changes to a document for the student to accept or
    reject one by one. Never applies anything."""
    data = dict(tool_input)
    document_id = data.pop("document_id")
    kind = want or data.pop("kind", None) or None
    doc = await cv_service.get_document_or_404(session, document_id, user_id)
    if (err := _kind_error(doc, kind)) is not None:
        return err
    version_id = data.pop("version_id", None) or None
    items = [cv_schemas.SuggestionIn(**item) for item in data.pop("suggestions")]
    if data:
        return {"error": f"Unknown fields: {sorted(data)}."}
    if version_id:
        version = await cv_service.get_version_or_404(session, version_id, user_id)
        text = version.markdown or ""
    else:
        text = doc.markdown or ""
    # A quote not in the text exactly once is never stored: it could only
    # be applied loosely, which never happens.
    ok = [cv_service.anchor(text, i.find) is not None for i in items]
    quoted = [i for i, good in zip(items, ok, strict=True) if good]
    rows = []
    if quoted:
        rows = await cv_service.create_suggestions(
            session,
            user_id,
            document_id,
            cv_schemas.SuggestionsCreate(version_id=version_id, suggestions=quoted),
        )
    stored = iter(rows)
    out = []
    for item, good in zip(items, ok, strict=True):
        if good:
            r = next(stored)
            entry = {
                "id": r["id"],
                "applicable": r["applicable"],
                "new_terms": (r.get("claim_check") or {}).get("new_terms") or [],
            }
            if (r.get("limit_check") or {}).get("over_limit"):
                entry["over_limit"] = True
            out.append(entry)
        else:
            out.append({"id": None, "applicable": False, "stored": False, "find": item.find[:200]})
    note = (
        "Stored for the student's review in the editor. One that wasn't stored "
        "quotes text that isn't in the document exactly once: re-read it and "
        "suggest it again with an exact quote."
    )
    over = next((r["limit_check"] for r in rows if (r.get("limit_check") or {}).get("over_limit")), None)
    if over:
        note += (
            f" Together these leave it at {over['words_after']} words"
            + (f" against a {over['word_limit']}-word limit" if over.get("word_limit") else "")
            + (f", {over['pages_after']} pages against {over['page_limit']}" if over.get("page_limit") else "")
            + ": the ones that add words are flagged over the limit. Suggest a cut "
            "elsewhere in the same call, or tell the student."
        )
    return {"suggestions": out, "note": note}


# Legacy CV tools: the document tools for kind=cv, results unchanged.


async def _cv_list_documents(tool_input: dict, session, user_id) -> dict:
    """The student's base CVs, each with its tailored versions."""
    del tool_input
    listed = await _list_documents({"kind": "cv"}, session, user_id)
    return {
        "documents": [
            {
                "id": d["id"],
                "title": d["title"],
                "updated_at": d["updated_at"],
                "versions": [
                    {k: v[k] for k in ("id", "name", "candidate_id", "tailored_for")}
                    for v in d["versions"]
                ],
            }
            for d in listed["documents"]
        ]
    }


async def _cv_read(tool_input: dict, session, user_id) -> dict:
    """A CV's Markdown: the base CV, or one tailored version of it."""
    out = await _read_document(tool_input, session, user_id, want="cv")
    out.pop("kind", None)
    out.pop("application_id", None)
    return out


async def _cv_suggest_changes(tool_input: dict, session, user_id) -> dict:
    tool_input.pop("kind", None)
    return await _suggest_changes(tool_input, session, user_id, want="cv")


async def _cv_get_application_context(tool_input: dict, session, user_id) -> dict:
    """Everything the assistant needs to tailor a CV for one tracked
    application: target, requirements, and the linked professors resolved
    to their scored candidate summaries where available."""
    app = await application_service.get_application_or_404(
        session, tool_input["application_id"], user_id
    )
    d = application_service.to_out(app)
    professors = []
    for p in (d.get("professors") or [])[:_SUMMARY_LIMIT]:
        entry = {"name": p.get("name"), "school": p.get("school")}
        candidate_id = p.get("candidate_id")
        if candidate_id:
            try:
                c = await candidate_service.get_candidate_detail(
                    session, user_id, candidate_id
                )
                entry["candidate"] = {
                    "professor_name": c.get("professor_name"),
                    "school_name": c.get("school_name"),
                    "program_name": c.get("program_name"),
                    "similarity_score": c.get("similarity_score"),
                    "status": c.get("status"),
                }
            except Exception:  # noqa: BLE001 - stale link degrades, doesn't fail
                entry["candidate"] = None
        professors.append(entry)
    return {
        "id": d["id"],
        "school": d.get("school"),
        "program": d.get("program"),
        "degree_type": d.get("degree_type"),
        "location": d.get("location"),
        "link": d.get("link"),
        "deadline": d.get("deadline"),
        "status": d.get("status"),
        "requirements": d.get("requirements") or [],
        "offer": (d.get("offer") or "")[:1000],
        "professors": professors,
    }


async def _cv_list_suggestions(tool_input: dict, session, user_id) -> dict:
    rows = await cv_service.list_suggestions(
        session,
        user_id,
        tool_input.get("document_id"),
        tool_input.get("version_id"),
        tool_input.get("status"),
    )
    return {
        "suggestions": [
            {
                "id": r["id"],
                "version_id": r["version_id"],
                "status": r["status"],
                "applicable": r["applicable"],
                "find": r["find"][:300],
                "replace": r["replace"][:300],
                "new_terms": (r.get("claim_check") or {}).get("new_terms") or [],
            }
            for r in rows[-_SUMMARY_LIMIT * 2 :]
        ]
    }


async def _get_draft(tool_input: dict, session, user_id) -> dict:
    draft = await outreach_service.get_draft_or_404(session, tool_input["draft_id"], user_id)
    d = await outreach_service.draft_out(session, user_id, draft)
    d["body"] = (d.get("body") or "")[:1500]
    d["created_at"] = str(d.get("created_at") or "") or None
    return d


async def _get_document_card(tool_input: dict, session, user_id) -> dict:
    doc = await cv_service.get_document_or_404(session, tool_input["document_id"], user_id)
    return {"id": doc.id, "title": doc.title, "kind": doc.kind or "cv"}


async def _get_paper(tool_input: dict, session, user_id) -> dict:
    from api.core.exceptions import NotFoundError
    from api.prospects.models import Paper, Professor

    row = (await session.execute(
        select(Paper, Professor.name)
        .join(Professor, Professor.id == Paper.professor_id)
        .where(Paper.id == tool_input["paper_id"], Paper.user_id == user_id)
    )).first()
    if row is None:
        raise NotFoundError("Paper not found")
    paper, professor = row
    return {"id": paper.id, "title": paper.title, "year": paper.year, "url": paper.url,
            "abstract": (paper.abstract or "")[:600] or None,
            "professor_id": paper.professor_id, "professor": professor}


SHOW_MAX = 12

#: What show_record can put in front of the student: the read that
#: fetches each kind, and the id argument that read takes.
SHOWABLE = {
    "candidate": (_get_candidate, "candidate_id"),
    "professor": (crud_tools.HANDLERS["get_professor"], "professor_id"),
    "school": (crud_tools.HANDLERS["get_school"], "school_id"),
    "program": (crud_tools.HANDLERS["get_program"], "program_id"),
    "application": (_get_application, "application_id"),
    "draft": (_get_draft, "draft_id"),
    "run": (_get_run, "run_id"),
    "document": (_get_document_card, "document_id"),
    "paper": (_get_paper, "paper_id"),
}


async def _show_record(tool_input: dict, session, user_id) -> dict:
    """Put records in front of the student as cards they can open.
    The other reads stay silent: a card appears only when the
    student asked to see something, or Gradis suggests looking at it."""
    kind = tool_input.get("kind")
    if kind not in SHOWABLE:
        return {"error": f"Unknown kind {kind!r}; use one of: {', '.join(SHOWABLE)}."}
    ids = tool_input.get("ids") or [tool_input.get("id")]
    ids = list(dict.fromkeys(i for i in ids if isinstance(i, str) and i))[:SHOW_MAX]
    if not ids:
        return {"error": "Give the id of at least one record to show."}
    from api.core.exceptions import NotFoundError

    read, key = SHOWABLE[kind]
    records, missing = [], []
    for i in ids:
        try:
            records.append(await read({key: i}, session, user_id))
        except NotFoundError:
            missing.append(i)
    if not records:
        return {"error": f"No {kind} found with those ids."}
    return {"kind": kind, "shown": len(records), "records": records, **({"not_found": missing} if missing else {})}


HANDLERS = {
    "list_runs": _list_runs,
    "get_run": _get_run,
    "list_candidates": _list_candidates,
    "get_candidate": _get_candidate,
    "list_programs": _list_programs,
    "list_tasks": _list_tasks,
    "list_applications": _list_applications,
    "get_application": _get_application,
    "list_drafts": _list_drafts,
    "list_candidate_drafts": _list_candidate_drafts,
    "search_web": _search_web,
    "fetch_page": _fetch_page,
    "find_openalex_author": _find_openalex_author,
    "get_author_works": _get_author_works,
    "score_alignment": _score_alignment,
    "save_program": _save_program,
    "save_application": _save_application,
    "save_email_draft": _save_email_draft,
    "review_candidate": _review_candidate,
    "update_application": _update_application,
    "update_draft": _update_draft,
    "list_documents": _list_documents,
    "read_document": _read_document,
    "suggest_changes": _suggest_changes,
    "cv_list_documents": _cv_list_documents,
    "cv_read": _cv_read,
    "cv_get_application_context": _cv_get_application_context,
    "cv_suggest_changes": _cv_suggest_changes,
    "cv_list_suggestions": _cv_list_suggestions,
    "show_record": _show_record,
    # CRUD over every entity plus global search (api/assistant/crud_tools.py).
    **crud_tools.HANDLERS,
}


#: The fabrication rule, the same for every kind of document.
_SUGGEST_RULES = (
    "Rephrase, reorder and sharpen only what the student's documents already "
    "say or what they told you in this chat: never add experience, results, "
    "skills, publications, awards, dates or funding. Words their documents never "
    "mention are flagged to the student. Nothing changes until they accept. "
    "When the document has a word or page limit (read_document shows it), "
    "a suggestion that adds words comes with a cut elsewhere in the same call "
    "that keeps it within the limit; otherwise it is flagged over the limit."
)

ASSISTANT_DEFINITIONS = [
    {
        "name": "list_runs",
        "description": "List recent research runs with task counts and candidate counts.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_run",
        "description": "Get one run's status, field/region, task counts, and candidate count.",
        "parameters": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
    },
    {
        "name": "list_candidates",
        "description": "A run's professor candidates (its matches), best fit first.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["discovered", "researched", "scored", "drafted", "approved", "rejected", "sent"],
                },
                "limit": {"type": "integer"},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "get_candidate",
        "description": "Full review record for one candidate: papers, rationale, draft.",
        "parameters": {
            "type": "object",
            "properties": {"candidate_id": {"type": "string"}},
            "required": ["candidate_id"],
        },
    },
    {
        "name": "list_programs",
        "description": "Discovery tree for a run: schools with programs and professor counts.",
        "parameters": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
    },
    {
        "name": "list_tasks",
        "description": "Recent research tasks for a run with status and errors.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "list_applications",
        "description": "Tracked graduate applications (school, program, deadline, status).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_application",
        "description": "Full tracker entry for one application.",
        "parameters": {
            "type": "object",
            "properties": {"application_id": {"type": "string"}},
            "required": ["application_id"],
        },
    },
    {
        "name": "list_drafts",
        "description": "Email drafts queued for a run.",
        "parameters": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
    },
    {
        "name": "list_candidate_drafts",
        "description": "Every email draft saved for one candidate (a candidate can hold several).",
        "parameters": {
            "type": "object",
            "properties": {"candidate_id": {"type": "string"}},
            "required": ["candidate_id"],
        },
    },
    {
        "name": "search_web",
        "description": "Search the web for program pages, faculty listings, deadlines.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "fetch_page",
        "description": "Fetch the cleaned text of a web page (faculty listing, admissions page). Long pages end with the offset to read on from.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
            },
            "required": ["url"],
        },
    },
    {
        "name": "find_openalex_author",
        "description": "Search OpenAlex for a researcher by name, optionally with institution_hint.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "institution_hint": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_author_works",
        "description": "Get an OpenAlex author's recent publications with abstracts.",
        "parameters": {
            "type": "object",
            "properties": {"openalex_id": {"type": "string"}},
            "required": ["openalex_id"],
        },
    },
    {
        "name": "score_alignment",
        "description": "Deterministic similarity between an interest statement and paper abstracts.",
        "parameters": {
            "type": "object",
            "properties": {
                "interest_text": {"type": "string"},
                "abstracts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["interest_text", "abstracts"],
        },
    },
    {
        "name": "save_program",
        "description": "Save a school + graduate program into a run (queues faculty research).",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "school_name": {"type": "string"},
                "school_country": {"type": "string"},
                "school_website": {"type": "string"},
                "school_image_url": {
                    "type": "string",
                    "description": "The school's logo or a campus photo, as a direct image URL.",
                },
                "program_name": {"type": "string"},
                "department_url": {"type": "string"},
            },
            "required": ["run_id", "school_name", "program_name"],
        },
    },
    {
        "name": "save_application",
        "description": "Index a researched application (deadline, requirements) into the tracker.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "school": {"type": "string"},
                "program": {"type": "string"},
                "degree_type": {"type": "string"},
                "location": {"type": "string"},
                "link": {"type": "string"},
                "deadline": {"type": "string"},
                "requirements": {"type": "array", "items": {"type": "string"}},
                "offer": {"type": "string"},
                "fee_waiver": {"type": "boolean"},
                "fee_waiver_notes": {"type": "string"},
                "professors": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["run_id", "school", "notes"],
        },
    },
    {
        "name": "save_email_draft",
        "description": "Save a personalized cold email draft for a candidate (never sends).",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["candidate_id", "subject", "body"],
        },
    },
    {
        "name": "review_candidate",
        "description": "Approve or reject a candidate (marks reviewed, never sends email).",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "approved": {"type": "boolean"},
            },
            "required": ["candidate_id", "approved"],
        },
    },
    {
        "name": "update_application",
        "description": "Update a tracked application's fields (status, deadline, notes, ...).",
        "parameters": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "status": {"type": "string"},
                "deadline": {"type": "string"},
                "notes": {"type": "string"},
                "location": {"type": "string"},
                "link": {"type": "string"},
                "offer": {"type": "string"},
            },
            "required": ["application_id"],
        },
    },
    {
        "name": "update_draft",
        "description": "Edit a saved email draft's subject and/or body.",
        "parameters": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": "list_documents",
        "description": (
            "List the student's documents (CVs, statements of purpose, diversity "
            "statements, research proposals, interest statements, notes), each with its tailored versions "
            "and folder. Filter by kind or folder_id. Outreach emails are Outbox drafts, "
            "not documents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(_KINDS)},
                "folder_id": {"type": "string"},
            },
        },
    },
    {
        "name": "read_document",
        "description": (
            "Read a document as Markdown: the base text (document_id only) or a "
            "tailored version (with version_id). Read it before suggesting changes, "
            "and quote its text exactly in them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "version_id": {"type": "string"},
                "kind": {"type": "string", "enum": list(_KINDS)},
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "suggest_changes",
        "description": (
            "Suggest changes to a document of any kind (a tailored version, or the "
            "base text when no version_id is given) for the student to accept, edit "
            "or reject one by one. Each suggestion replaces `find` (an exact quote of "
            "the current text, appearing once) with `replace`; to reorder, quote the "
            "whole passage and give it in the new order. "
            + _SUGGEST_RULES
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "version_id": {"type": "string"},
                "kind": {"type": "string", "enum": list(_KINDS)},
                "suggestions": {
                    "type": "array",
                    "maxItems": 20,
                    "items": {
                        "type": "object",
                        "properties": {
                            "find": {"type": "string"},
                            "replace": {"type": "string"},
                            "rationale": {"type": "string"},
                        },
                        "required": ["find", "replace"],
                    },
                },
            },
            "required": ["document_id", "suggestions"],
        },
    },
    {
        "name": "cv_list_documents",
        "description": "List the student's base CVs, each with its tailored versions (name, who it was tailored for).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "cv_read",
        "description": (
            "Read a CV as Markdown: the base CV (document_id only) or a tailored "
            "version (with version_id). Read it before suggesting changes, and "
            "quote its text exactly in them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "version_id": {"type": "string"},
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "cv_get_application_context",
        "description": "Target school/program, requirements, deadline, and linked professor summaries for tailoring a CV to one tracked application.",
        "parameters": {
            "type": "object",
            "properties": {"application_id": {"type": "string"}},
            "required": ["application_id"],
        },
    },
    {
        "name": "cv_suggest_changes",
        "description": (
            "Suggest changes to a CV (a tailored version, or the base CV when no "
            "version_id is given) for the student to accept, edit or reject one "
            "by one. Each suggestion replaces `find` (an exact quote of the CV's "
            "current text, appearing once) with `replace`; to reorder, quote the "
            "whole passage and give it in the new order. Rephrase, reorder and "
            "sharpen only what the CV already says: never add experience, "
            "results or skills. Words the base CV never mentions are flagged to "
            "the student. Nothing changes until they accept."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "version_id": {"type": "string"},
                "suggestions": {
                    "type": "array",
                    "maxItems": 20,
                    "items": {
                        "type": "object",
                        "properties": {
                            "find": {"type": "string"},
                            "replace": {"type": "string"},
                            "rationale": {"type": "string"},
                        },
                        "required": ["find", "replace"],
                    },
                },
            },
            "required": ["document_id", "suggestions"],
        },
    },
    {
        "name": "cv_list_suggestions",
        "description": "List suggested CV changes (optionally for one version or status) and whether each was accepted, rejected or is still pending.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "version_id": {"type": "string"},
                "status": {"type": "string"},
            },
        },
    },
    {
        "name": "show_record",
        "description": (
            "Show the student records of one kind as cards they can click to open. Use it "
            "instead of get_* whenever they ask for a record itself: to see, show, retrieve, "
            "get, fetch, pull up or open it (\"retrieve his record from the database\", "
            "\"show my applications\"), or when you suggest they look at specific records. "
            "Returns the full records, so no separate read is needed. Not for records you "
            "only read to answer a question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(SHOWABLE)},
                "ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": SHOW_MAX},
            },
            "required": ["kind", "ids"],
        },
    },
    *crud_tools.DEFINITIONS,
]


async def invoke(
    tool_name: str, tool_input: dict, session, user_id=None, *, approved: bool = False
) -> dict:
    """One Gradis tool call. Never raises: failures come back as error results.
    Confirm-gated tools (CONFIRM_TOOLS or the account's setting) are refused
    unless `approved`; the gate lives here so no caller can skip it."""
    from api.agents import registry as agents_registry

    if not approved and await agents_registry.assistant_confirm_required(
        session, user_id, tool_name
    ):
        return {
            "error": (
                f"{tool_name} needs the user's confirmation and was not run. "
                "Do not retry it without asking."
            )
        }

    state = await agents_registry.tool_state(
        session, user_id, agents_registry.ASSISTANT_SCOPE, tool_name
    )
    if not state["enabled"]:
        return {
            "error": (
                f"Tool {tool_name} is disabled by the operator; "
                "answer without it or say what is missing."
            )
        }
    handler = HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        result = await handler(dict(tool_input), session, user_id)
        if result is None:
            return {}
        return result
    except Exception as exc:  # noqa: BLE001 - surface to the model, don't kill the chat
        return {"error": f"{tool_name} failed: {exc}"}


#: Writes that never run without the user's approval. CV suggestions don't
#: confirm: they change nothing until accepted in the editor.
CONFIRM_TOOLS = frozenset(
    {
        "save_program",
        "save_application",
        "save_email_draft",
        "review_candidate",
        "update_application",
        "update_draft",
    }
    | crud_tools.CONFIRM
)


# A chat starts with reads only (CV suggestions count as reads); the write
# tools join once the stored history shows a write intent and then stay.

#: The write phase: everything that pauses for the user's approval.
WRITE_TOOLS = CONFIRM_TOOLS

ENABLE_CHANGES = "enable_changes"
ENABLE_CHANGES_DEFINITION = {
    "name": ENABLE_CHANGES,
    "description": (
        "Adds the tools that create, change, approve or delete the student's "
        "data (each still asks the user before it runs) for the rest of this "
        "chat. Call it first when the user asks for a change and those tools "
        "aren't in your list yet. Not needed to read, research, score or "
        "suggest document changes."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

#: Verbs that ask for a change. A false positive just offers the write
#: tools a turn early; a miss costs one enable_changes call.
_WRITE_WORDS = re.compile(
    r"\b(?:add|create|make|start|launch|update|change|edit|modify|rename|fix|"
    r"correct|set|mark|move|delete|remove|discard|drop|save|track|approve|"
    r"reject|accept|decline|pause|resume|cancel|stop|restart|rewrite|replace|"
    r"archive|draft|write|retune|rescore)\b",
    re.IGNORECASE,
)


def writes_unlocked(history: list[dict]) -> bool:
    """True once the conversation has shown a write intent."""
    for m in history:
        role = m.get("role")
        if role == "user" and isinstance(m.get("content"), str):
            if _WRITE_WORDS.search(m["content"]):
                return True
        elif role == "assistant":
            for tc in m.get("tool_calls") or []:
                if tc.get("name") == ENABLE_CHANGES or tc.get("name") in WRITE_TOOLS:
                    return True
    return False


#: Legacy CV tools: offered only to chats that already called one (a
#: provider may reject a history naming a tool it isn't offered).
LEGACY_TOOLS = frozenset({"cv_list_documents", "cv_read", "cv_suggest_changes"})


def without_unused_legacy(definitions: list[dict], history: list[dict]) -> list[dict]:
    """The definitions minus the legacy CV tools this chat never called."""
    used = {
        tc.get("name")
        for m in history
        if m.get("role") == "assistant"
        for tc in m.get("tool_calls") or []
    }
    return [
        d for d in definitions if d.get("name") not in LEGACY_TOOLS or d.get("name") in used
    ]


def phase_definitions(definitions: list[dict], unlocked: bool) -> list[dict]:
    """The reads, plus every write once unlocked. enable_changes is offered
    whenever any write is enabled, even after unlocking: a provider may reject
    a history naming a tool it isn't offered."""
    reads = [d for d in definitions if d.get("name") not in WRITE_TOOLS]
    if len(reads) == len(definitions):
        return definitions
    return [*(definitions if unlocked else reads), ENABLE_CHANGES_DEFINITION]


def describe_call(tool_name: str, tool_input: dict) -> str:
    """One-line human summary of a pending write, for the confirm card.
    Falls back to the tool name when the args don't match the shape."""
    get = tool_input.get
    crud = crud_tools.describe(tool_name, tool_input)
    if crud is not None:
        return crud
    if tool_name == "save_program":
        return f"Save program '{get('program_name')}' at {get('school_name')}"
    if tool_name == "save_application":
        return f"Track application for {get('school')}" + (
            f" — {get('program')}" if get("program") else ""
        )
    if tool_name == "save_email_draft":
        return f"Save email draft '{get('subject')}'"
    if tool_name == "review_candidate":
        verdict = "Approve" if get("approved") else "Reject"
        return f"{verdict} this candidate"
    if tool_name == "update_application":
        fields = [k for k in tool_input if k != "application_id"]
        return f"Update application ({', '.join(fields) or 'no fields'})"
    if tool_name == "update_draft":
        fields = [k for k in tool_input if k != "draft_id"]
        return f"Edit email draft ({', '.join(fields) or 'no fields'})"
    if tool_name == "fetch_page":
        return (
            f"Open {get('url')} — this link didn't come from you or a search, "
            "and your private data was read this turn"
        )
    return tool_name
