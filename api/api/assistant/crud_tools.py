"""Gradis CRUD over every entity, plus global search.

Handlers call the same service functions as the app's routes, so ownership
checks, guards, billing gates and notifications apply unchanged. Every write
is in CONFIRM_TOOLS.
"""

from api.applications import schemas as application_schemas
from api.applications import service as application_service
from api.assistant.search import KINDS, search_everything
from api.auth import models as auth_models
from api.billing import service as billing
from api.candidates import service as candidate_service
from api.outreach import service as outreach_service
from api.prospects import service as prospect_service
from api.providers import service as providers_service
from api.runs import removal as run_removal
from api.runs import service as run_service


def _pick(tool_input: dict, fields: set[str]) -> dict:
    """The given fields that are present (None means 'not given')."""
    return {k: v for k, v in tool_input.items() if k in fields and v is not None}


def _brief_professor(d: dict) -> dict:
    out = {k: d.get(k) for k in ("id", "name", "email", "profile_url", "lab_name", "openalex_id", "photo_url",
                                 "program_id", "program_name", "school_name", "candidate_id")}
    out["bio"] = (d.get("bio") or "")[:600] or None
    out["papers"] = [{"id": p.get("id"), "title": p.get("title"), "year": p.get("year"), "citations": p.get("citations")}
                     for p in (d.get("papers") or [])[:8]]
    return out


async def _search(tool_input: dict, session, user_id) -> dict:
    return await search_everything(
        session, user_id, tool_input.get("query", ""), tool_input.get("kinds"), tool_input.get("limit") or 5
    )


async def _list_schools(tool_input: dict, session, user_id) -> dict:
    del tool_input
    schools = await prospect_service.list_account_schools(session, user_id)
    return {
        "schools": [
            {"id": s["id"], "name": s["name"], "country": s.get("country"), "tier": s.get("tier"),
             "programs": len(s["programs"]), "runs": len(s.get("run_ids") or [])}
            for s in schools[:30]
        ],
        "total": len(schools),
    }


async def _get_school(tool_input: dict, session, user_id) -> dict:
    d = await prospect_service.get_school(session, user_id, tool_input["school_id"])
    d["faculty"] = [
        {"id": f["id"], "name": f["name"], "program": f["program"], "candidate_id": f["candidate_id"],
         "similarity_score": f.get("similarity_score")}
        for f in (await prospect_service.school_faculty(session, user_id, d["id"]))[:30]
    ]
    return d


async def _get_program(tool_input: dict, session, user_id) -> dict:
    d = await prospect_service.get_program(session, user_id, tool_input["program_id"])
    d["professors"] = [{"id": p["id"], "name": p["name"]} for p in (d.get("professors") or [])[:30]]
    return d


async def _get_professor(tool_input: dict, session, user_id) -> dict:
    return _brief_professor(await prospect_service.get_professor(session, user_id, tool_input["professor_id"]))


async def _create_run(tool_input: dict, session, user_id) -> dict:
    max_professors = await billing.gate_new_run(session, user_id, tool_input.get("max_professors"))
    run = await run_service.create_run(
        session,
        user_id,
        region=tool_input.get("region") or "Anywhere",
        field=tool_input.get("field") or "",
        degree_level=tool_input.get("degree_level") or "phd",
        interest_statement=tool_input["interest_statement"],
        max_programs=tool_input.get("max_programs"),
        max_professors=max_professors,
        llm_provider=await providers_service.run_provider(session, user_id, None),
    )
    return {"run_id": run.id, "status": run.status, "note": "Discovery is queued; the worker starts on it shortly."}


async def _update_run(tool_input: dict, session, user_id) -> dict:
    data = _pick(tool_input, {"interest_statement", "max_programs", "max_professors", "max_professors_per_program"})
    if not data:
        return {"error": "Nothing to update: give interest_statement or a budget."}
    if "max_professors" in data:
        user = await session.get(auth_models.User, user_id)
        data["max_professors"] = billing.cap_per_run(user, data["max_professors"])
    run = await run_service.update_run(session, user_id, tool_input["run_id"], data)
    return {"run_id": run.id, "updated": sorted(data)}


async def _set_run_status(tool_input: dict, session, user_id) -> dict:
    action = str(tool_input.get("action") or "").lower()
    if action == "resume":
        return await run_service.resume_run(session, user_id, tool_input["run_id"])
    status = {"pause": "paused", "cancel": "cancelled"}.get(action)
    if status is None:
        return {"error": "action must be pause, resume or cancel."}
    return await run_service.set_run_status(session, user_id, tool_input["run_id"], status)


async def _delete_run(tool_input: dict, session, user_id) -> dict:
    return await run_removal.delete_run(session, user_id, tool_input["run_id"])


async def _create_school(tool_input: dict, session, user_id) -> dict:
    programs = [{"name": p} if isinstance(p, str) else p for p in (tool_input.get("programs") or [])]
    return await prospect_service.create_school(
        session, user_id, tool_input["run_id"], name=tool_input["name"], country=tool_input.get("country"),
        website_url=tool_input.get("website_url"), programs=programs,
    )


async def _update_school(tool_input: dict, session, user_id) -> dict:
    data = _pick(tool_input, set(prospect_service.SCHOOL_MUTABLE))
    if not data:
        return {"error": "Nothing to update: give name, country or website_url."}
    return await prospect_service.update_school(session, user_id, tool_input["school_id"], data)


async def _delete_school(tool_input: dict, session, user_id) -> dict:
    return await prospect_service.delete_school(session, user_id, tool_input["school_id"])


async def _create_program(tool_input: dict, session, user_id) -> dict:
    return await prospect_service.create_program(
        session, user_id, tool_input["school_id"], name=tool_input["name"],
        department_url=tool_input.get("department_url"),
    )


async def _update_program(tool_input: dict, session, user_id) -> dict:
    data = _pick(tool_input, set(prospect_service.PROGRAM_MUTABLE))
    if not data:
        return {"error": "Nothing to update: give name or department_url."}
    return await prospect_service.update_program(session, user_id, tool_input["program_id"], data)


async def _delete_program(tool_input: dict, session, user_id) -> dict:
    return await prospect_service.delete_program(session, user_id, tool_input["program_id"])


async def _create_professor(tool_input: dict, session, user_id) -> dict:
    d = await prospect_service.create_professor(
        session, user_id, tool_input["program_id"], name=tool_input["name"],
        profile_url=tool_input.get("profile_url"), email=tool_input.get("email"),
        openalex_id=tool_input.get("openalex_id"),
    )
    return {**_brief_professor(d), "note": "Queued for research: OpenAlex lookup and scoring run in the worker."}


async def _update_professor(tool_input: dict, session, user_id) -> dict:
    data = _pick(tool_input, set(prospect_service.PROFESSOR_MUTABLE) - {"socials"})
    if not data:
        return {"error": "Nothing to update: give at least one field."}
    return _brief_professor(await prospect_service.update_professor(session, user_id, tool_input["professor_id"], data))


async def _save_professor_papers(tool_input: dict, session, user_id) -> dict:
    d = await prospect_service.save_professor_papers(session, user_id, tool_input["professor_id"], tool_input["openalex_id"])
    return {**_brief_professor(d), "papers_added": d["papers_added"]}


async def _delete_professor(tool_input: dict, session, user_id) -> dict:
    return await prospect_service.delete_professor(session, user_id, tool_input["professor_id"])


async def _update_candidate(tool_input: dict, session, user_id) -> dict:
    data = _pick(tool_input, {"status", "rationale"})
    if not data:
        return {"error": "Nothing to update: give status and/or rationale."}
    d = await candidate_service.update_candidate(session, user_id, tool_input["candidate_id"], data)
    return {k: d.get(k) for k in ("id", "professor_name", "status", "rationale", "similarity_score")}


async def _delete_candidate(tool_input: dict, session, user_id) -> dict:
    return await candidate_service.delete_candidate(session, user_id, tool_input["candidate_id"])


async def _delete_draft(tool_input: dict, session, user_id) -> dict:
    return await outreach_service.delete_draft(session, user_id, tool_input["draft_id"])


_APPLICATION_FIELDS = {"school", "program", "degree_type", "location", "link", "offer", "deadline",
                       "status", "notes", "fee_waiver", "fee_waiver_notes"}


async def _create_application(tool_input: dict, session, user_id) -> dict:
    data = _pick(tool_input, _APPLICATION_FIELDS)
    if tool_input.get("requirements"):
        data["requirements"] = [{"label": str(r), "done": False} for r in tool_input["requirements"]]
    if tool_input.get("professors"):
        data["professors"] = [{"name": str(n)} for n in tool_input["professors"]]
    d = await application_service.create_application(
        session, user_id, application_schemas.ApplicationCreate(**data)
    )
    return {k: d.get(k) for k in ("id", "school", "program", "status", "deadline")}


async def _delete_application(tool_input: dict, session, user_id) -> dict:
    return await application_service.delete_application(session, user_id, tool_input["application_id"])


HANDLERS = {
    "search": _search,
    "list_schools": _list_schools,
    "get_school": _get_school,
    "get_program": _get_program,
    "get_professor": _get_professor,
    "create_run": _create_run,
    "update_run": _update_run,
    "set_run_status": _set_run_status,
    "delete_run": _delete_run,
    "create_school": _create_school,
    "update_school": _update_school,
    "delete_school": _delete_school,
    "create_program": _create_program,
    "update_program": _update_program,
    "delete_program": _delete_program,
    "create_professor": _create_professor,
    "update_professor": _update_professor,
    "save_professor_papers": _save_professor_papers,
    "delete_professor": _delete_professor,
    "update_candidate": _update_candidate,
    "delete_candidate": _delete_candidate,
    "delete_draft": _delete_draft,
    "create_application": _create_application,
    "delete_application": _delete_application,
}

#: Every write above: they run only after the user accepts the card.
CONFIRM = frozenset(set(HANDLERS) - {"search", "list_schools", "get_school", "get_program", "get_professor"})


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


_S = {"type": "string"}
_I = {"type": "integer"}

DEFINITIONS = [
    {
        "name": "search",
        "description": "Search everything the student has (runs, schools, programs, professors, candidates, applications, drafts) by name or text. Use it to find ids before reading or changing something.",
        "parameters": _obj({"query": _S, "kinds": {"type": "array", "items": {"type": "string", "enum": list(KINDS)}}, "limit": _I}, ["query"]),
    },
    {"name": "list_schools", "description": "Every school the student has, once each, with programme and run counts.", "parameters": _obj({}, [])},
    {"name": "get_school", "description": "One school: details, programmes, and faculty across runs with candidate scores.", "parameters": _obj({"school_id": _S}, ["school_id"])},
    {"name": "get_program", "description": "One programme: department page and its professors.", "parameters": _obj({"program_id": _S}, ["program_id"])},
    {"name": "get_professor", "description": "One professor: contact, lab, links, bio, papers, and candidate id when scored.", "parameters": _obj({"professor_id": _S}, ["professor_id"])},
    {
        "name": "create_run",
        "description": "Start a new research run (discovery, then faculty research). Counts against the student's plan.",
        "parameters": _obj({"interest_statement": _S, "field": _S, "region": _S, "degree_level": _S, "max_programs": _I, "max_professors": _I}, ["interest_statement"]),
    },
    {
        "name": "update_run",
        "description": "Change a run's interest statement or budgets; later saves and scores use the new values.",
        "parameters": _obj({"run_id": _S, "interest_statement": _S, "max_programs": _I, "max_professors": _I, "max_professors_per_program": _I}, ["run_id"]),
    },
    {"name": "set_run_status", "description": "Pause, resume or cancel a run.", "parameters": _obj({"run_id": _S, "action": {"type": "string", "enum": ["pause", "resume", "cancel"]}}, ["run_id", "action"])},
    {"name": "delete_run", "description": "Delete a run with its tasks, candidates and drafts; schools other runs use are kept.", "parameters": _obj({"run_id": _S}, ["run_id"])},
    {
        "name": "create_school",
        "description": "Add a school to a run (optionally with programmes, each queued for faculty research). Reuses the student's existing school of the same name.",
        "parameters": _obj({"run_id": _S, "name": _S, "country": _S, "website_url": _S, "programs": {"type": "array", "items": {"type": "string"}}}, ["run_id", "name"]),
    },
    {"name": "update_school", "description": "Edit a school's name, country or website.", "parameters": _obj({"school_id": _S, "name": _S, "country": _S, "website_url": _S}, ["school_id"])},
    {"name": "delete_school", "description": "Delete a school and its programmes and unscored professors. Refused while any professor there has a candidate.", "parameters": _obj({"school_id": _S}, ["school_id"])},
    {"name": "create_program", "description": "Add a programme to a school; its faculty research is queued.", "parameters": _obj({"school_id": _S, "name": _S, "department_url": _S}, ["school_id", "name"])},
    {"name": "update_program", "description": "Edit a programme's name or department page.", "parameters": _obj({"program_id": _S, "name": _S, "department_url": _S}, ["program_id"])},
    {"name": "delete_program", "description": "Delete a programme and its unscored professors. Refused while any professor there has a candidate.", "parameters": _obj({"program_id": _S}, ["program_id"])},
    {"name": "create_professor", "description": "Add a professor to a programme; they're queued for OpenAlex lookup and scoring.", "parameters": _obj({"program_id": _S, "name": _S, "profile_url": _S, "email": _S, "openalex_id": _S}, ["program_id", "name"])},
    {
        "name": "update_professor",
        "description": "Edit a professor's details (name, email, profile link, lab, bio, photo, OpenAlex id).",
        "parameters": _obj({"professor_id": _S, "name": _S, "email": _S, "profile_url": _S, "lab_name": _S, "bio": _S, "photo_url": _S, "openalex_id": _S}, ["professor_id"]),
    },
    {
        "name": "save_professor_papers",
        "description": (
            "Store a professor's recent papers from OpenAlex. Find the right author first "
            "(find_openalex_author, checking the institution), then pass their id; the papers "
            "are fetched here, so never type them in."
        ),
        "parameters": _obj({"professor_id": _S, "openalex_id": _S}, ["professor_id", "openalex_id"]),
    },
    {"name": "delete_professor", "description": "Delete a professor and their papers. Refused while they have a candidate (delete the candidate first).", "parameters": _obj({"professor_id": _S}, ["professor_id"])},
    {
        "name": "update_candidate",
        "description": "Change a candidate's status (scored, approved, rejected, sent) or rewrite its rationale. The fit score can't be edited.",
        "parameters": _obj({"candidate_id": _S, "status": {"type": "string", "enum": ["scored", "approved", "rejected", "sent"]}, "rationale": _S}, ["candidate_id"]),
    },
    {"name": "delete_candidate", "description": "Discard a candidate and its drafts (e.g. a wrong-person match). The professor and papers stay.", "parameters": _obj({"candidate_id": _S}, ["candidate_id"])},
    {"name": "delete_draft", "description": "Discard an email draft; its candidate goes back to scored.", "parameters": _obj({"draft_id": _S}, ["draft_id"])},
    {
        "name": "create_application",
        "description": "Track a new application by hand (no run needed).",
        "parameters": _obj({
            "school": _S, "program": _S, "degree_type": _S, "location": _S, "link": _S, "deadline": {"type": "string", "description": "YYYY-MM-DD"},
            "status": {"type": "string", "enum": ["wishlist", "applying", "submitted", "interview", "offer", "rejected"]},
            "requirements": {"type": "array", "items": {"type": "string"}}, "professors": {"type": "array", "items": {"type": "string"}},
            "offer": _S, "notes": _S, "fee_waiver": {"type": "boolean"}, "fee_waiver_notes": _S,
        }, ["school"]),
    },
    {"name": "delete_application", "description": "Remove an application from the tracker.", "parameters": _obj({"application_id": _S}, ["application_id"])},
]


def describe(tool_name: str, tool_input: dict) -> str | None:
    """Confirmation-card summary for the writes above; None for others."""
    get = tool_input.get
    fields = lambda *skip: ", ".join(k for k in tool_input if k not in skip) or "no fields"
    return {
        "create_run": f"Start a new run: {(get('interest_statement') or '')[:80]}",
        "update_run": f"Update run ({fields('run_id')})",
        "set_run_status": f"{str(get('action') or '').capitalize()} this run",
        "delete_run": "Delete this run with its tasks, candidates and drafts",
        "create_school": f"Add {get('name')} to the run",
        "update_school": f"Update school ({fields('school_id')})",
        "delete_school": "Delete this school and its programmes",
        "create_program": f"Add programme '{get('name')}'",
        "update_program": f"Update programme ({fields('program_id')})",
        "delete_program": "Delete this programme",
        "create_professor": f"Add professor {get('name')} and research them",
        "update_professor": f"Update professor ({fields('professor_id')})",
        "save_professor_papers": "Save this professor's papers from OpenAlex",
        "delete_professor": "Delete this professor and their papers",
        "update_candidate": f"Update candidate ({fields('candidate_id')})",
        "delete_candidate": "Discard this candidate and its drafts",
        "delete_draft": "Discard this email draft",
        "create_application": f"Track an application for {get('school')}" + (f", {get('program')}" if get("program") else ""),
        "delete_application": "Remove this application from the tracker",
    }.get(tool_name)
