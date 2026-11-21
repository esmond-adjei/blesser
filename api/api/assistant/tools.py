from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select

from api import web
from api.applicant_kit import models as kit_models
from api.applicant_kit import service as kit
from api.applicant_kit.schemas import http_url
from api.applications import service as applications
from api.applications.schemas import ApplicationUpdate
from api.assistant import edits
from api.assistant.sources import SourceRegistry
from api.core.exceptions import NotFoundError
from api.core.time import human_day
from api.opportunities import service as opportunities
from api.opportunities.models import OpportunityCategory, OpportunityKind
from api.todos import service as todos
from api.todos.schemas import TodoCreate

Query = Annotated[str, StringConstraints(strip_whitespace=True, max_length=180)]
RequiredQuery = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)
]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogSearch(ToolInput):
    query: Query = ""
    category: OpportunityCategory | None = None
    kind: OpportunityKind | None = None
    country: Query | None = None
    include_closed: bool = False
    closing_within: int | None = Field(default=None, ge=0, le=365)


class OpportunityLookup(ToolInput):
    opportunity_id: RequiredQuery


class ApplicationLookup(ToolInput):
    application_id: RequiredQuery


class ApplicationChanges(ApplicationUpdate):
    model_config = ConfigDict(extra="forbid")


class UpdateApplication(ApplicationLookup):
    changes: ApplicationChanges


class MemberLookup(ToolInput):
    query: Query = ""


class TodoLookup(MemberLookup):
    status: Literal["open", "done", "all"] = "open"


class KitLookup(MemberLookup):
    section: Literal["profile", "projects", "documents", "answers"]


class WebSearch(ToolInput):
    query: RequiredQuery


class AddTodo(ToolInput):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    due_date: date | None = None


PRIVATE_TOOLS = frozenset(
    {"list_applications", "get_application", "list_todos", "read_apply_kit"}
)
WRITES = frozenset({"track_opportunity", "add_todo", "update_application"})
CATALOG_TOOLS = frozenset({"search_catalog", "get_opportunity"})
TOOLS = {
    "search_catalog": (
        CatalogSearch,
        "Search the member opportunity catalog by a few keywords and optional filters. Use a blank query for broad or deadline searches.",
    ),
    "get_opportunity": (
        OpportunityLookup,
        "Read one published opportunity by a catalog id or slug.",
    ),
    "list_applications": (
        MemberLookup,
        "Read the current member's applications, optionally by title, organization or status.",
    ),
    "get_application": (
        ApplicationLookup,
        "Read the authenticated member's saved application details by application_id, including notes, link, benefits and requirements. Saved details remain readable even when the linked catalog record is unavailable. This does not grant access to unpublished catalog content.",
    ),
    "update_application": (
        UpdateApplication,
        "Propose editing the member's own application. Only supplied fields change. Requirements replace the entire checklist, so read the application first and preserve existing completion states. Requires member approval before saving.",
    ),
    "list_todos": (
        TodoLookup,
        "Read the current member's to-dos, optionally by title and completion status.",
    ),
    "read_apply_kit": (
        KitLookup,
        "Read one section of the member's apply kit. Documents return metadata and the profile excludes contact details and sensitive fields.",
    ),
    "search_web": (
        WebSearch,
        "Search the public web for opportunity information after checking the catalog. Use public terms only. Results are search snippets.",
    ),
    "enable_changes": (
        ToolInput,
        "Enable proposals for this turn only after the member explicitly requests a change. Proposals each require UI approval.",
    ),
    "track_opportunity": (
        OpportunityLookup,
        "Propose tracking a catalog opportunity for the member.",
    ),
    "add_todo": (
        AddTodo,
        "Propose adding a to-do with a title and an optional member-requested date.",
    ),
}
LABELS = {
    "search_catalog": "Searched the Blesser catalog",
    "get_opportunity": "Checked an opportunity",
    "list_applications": "Checked your applications",
    "get_application": "Checked an application",
    "update_application": "Update application",
    "list_todos": "Checked your to-dos",
    "read_apply_kit": "Checked your apply kit",
    "search_web": "Searched the web",
    "enable_changes": "Prepared to propose a change",
    "track_opportunity": "Track opportunity",
    "add_todo": "Add a to-do",
}


TOOLS.update(edits.TOOLS)
LABELS.update(edits.LABELS)
WRITES = WRITES | frozenset(edits.TOOLS)


def definitions(*, catalog_checked, changes_enabled, web_allowed):
    return [
        {
            "name": name,
            "description": description,
            "parameters": schema.model_json_schema(),
        }
        for name, (schema, description) in TOOLS.items()
        if (
            (name != "search_web" or (web_allowed and catalog_checked))
            and (name not in WRITES or changes_enabled)
            and (name != "enable_changes" or not changes_enabled)
        )
    ]


def _record(row, fields):
    return {
        key: value[:900] if isinstance(value, str) else value
        for key in fields
        if (value := row.get(key)) is not None
    }


def _matching(rows, query, fields):
    terms = query.casefold().split()
    return [
        row
        for row in rows
        if all(
            term in " ".join(str(row.get(field, "")) for field in fields).casefold()
            for term in terms
        )
    ]


def _opportunity(registry, row):
    key = registry.register("opportunity", row, detail=row["organization"])
    return {
        **_record(
            row,
            (
                "id",
                "slug",
                "title",
                "organization",
                "summary",
                "category",
                "kind",
                "eligibility",
                "benefits",
                "location",
                "countries",
                "requirements",
                "is_open",
            ),
        ),
        "source": key,
        "deadline": registry.deadlines.get(key),
    }


async def _apply_kit(session, user_id, args, registry):
    if args.section == "profile":
        data = await session.scalar(
            select(kit_models.Profile.data).where(kit_models.Profile.user_id == user_id)
        )
        fields = (
            "education",
            "skills",
            "experience",
            "country_of_residence",
            "city",
            "short_bio",
            "headline",
            "pronouns",
        )
        return {"profile": _record(data or {}, fields)}, None
    if args.section == "projects":
        rows = await kit.projects(session, user_id)
        fields = ("id", "name", "tagline", "problem", "solution", "stage", "sector")
        kind, title_key = "project", "name"
    elif args.section == "documents":
        rows = await kit.documents(session, user_id)
        fields = ("id", "title", "kind", "is_default")
        kind, title_key = "document", "title"
    else:
        rows = await kit.answers(session, user_id, q=args.query)
        fields = ("id", "question", "answer", "tags")
        kind, title_key = "answer", "question"
    matches = _matching(rows, args.query, fields) if args.section != "answers" else rows
    records = [
        {
            **_record(row, fields),
            "source": registry.register(
                kind, row, title=row.get(title_key) or "Untitled"
            ),
        }
        for row in matches[:12]
    ]
    return {"items": records, "total": len(matches)}, len(matches)


async def read(session, user_id, name, args, registry: SourceRegistry):
    if name == "search_catalog":
        page = await opportunities.list_public(
            session,
            q=args.query,
            category=args.category,
            kind=args.kind,
            country=args.country,
            open_only=not args.include_closed,
            closing_within=args.closing_within,
            sort="relevance",
            limit=12,
        )
        page["items"] = [_opportunity(registry, row) for row in page["items"]]
        page["scope"] = (
            "Published catalog records only, not saved applications or unpublished records."
        )
        page["returned"] = len(page["items"])
        page["truncated"] = page["total"] > len(page["items"])
        if not page["items"]:
            page["message"] = (
                "No published records matched these filters. This does not mean the member has no matching saved application. Use list_applications or get_application for their saved details."
            )
        return page, page["total"]
    if name == "get_opportunity":
        row = opportunities.to_out(
            await opportunities.get_or_404(session, args.opportunity_id)
        )
        return _opportunity(registry, row), None
    if name == "list_applications":
        rows = await applications.list_applications(session, user_id)
        rows = _matching(rows, args.query, ("title", "organization", "status"))
        records = []
        for row in rows[:16]:
            status = (
                "Not this time"
                if row["status"] == "rejected"
                else row["status"].capitalize()
            )
            key = registry.register("application", row, detail=status)
            records.append(
                {
                    **_record(
                        row,
                        (
                            "id",
                            "title",
                            "organization",
                            "kind",
                            "requirements",
                            "opportunity_id",
                        ),
                    ),
                    "source": key,
                    "status": status,
                    "deadline": registry.deadlines.get(key),
                }
            )
        return {
            "items": records,
            "total": len(rows),
            "returned": len(records),
            "truncated": len(rows) > len(records),
            "scope": "The authenticated member's saved applications. Status is application progress, not catalog moderation. Use id as application_id with get_application or update_application. opportunity_id refers to a separate catalog record, which may be unavailable. Empty requirements mean no saved checklist, not that the opportunity has no requirements.",
        }, len(rows)
    if name == "get_application":
        row = applications.to_out(
            await applications.get_or_404(session, user_id, args.application_id)
        )
        key = registry.register("application", row, detail=row["status"])
        return {
            **row,
            "source": key,
            "deadline": registry.deadlines.get(key),
            "scope": "The authenticated member's saved application details. These are saved values, not newly verified catalog or web facts.",
        }, None
    if name == "list_todos":
        rows = await todos.list_todos(session, user_id, status=args.status)
        rows = _matching(
            rows, args.query, ("title", "opportunity_title", "application_label")
        )
        records = [
            {
                **_record(row, ("id", "title", "done", "due_date", "priority")),
                "source": registry.register(
                    "todo",
                    {**row, "deadline_date": row.get("due_date")},
                    detail="Done" if row["done"] else "Open",
                ),
            }
            for row in rows[:16]
        ]
        return {"items": records, "total": len(rows)}, len(rows)
    if name == "read_apply_kit":
        return await _apply_kit(session, user_id, args, registry)
    if name == "search_web":
        records = []
        for row in web.brief_results(await web.search_web(args.query)):
            url = str(row.get("url") or "")
            try:
                if not http_url(url):
                    continue
            except ValueError:
                continue
            title = str(row.get("title") or "Web result")
            key = registry.register("web", {"id": url, "title": title}, url=url)
            records.append(
                {"title": title, "snippet": row.get("snippet", ""), "source": key}
            )
        return {"items": records, "total": len(records)}, len(records)
    raise ValueError("Unknown read tool")


async def proposal(session, user_id, name, args):
    if name in edits.TOOLS:
        return await edits.proposal(session, user_id, name, args)
    if name == "update_application":
        app = await applications.get_or_404(session, user_id, args.application_id)
        patch = args.changes.model_dump(exclude_unset=True, mode="json")
        if not patch:
            raise ValueError("Supply at least one field to update.")
        return f"Update “{app.title}”?", {
            "application_id": app.id,
            "changes": patch,
        }
    if name == "track_opportunity":
        opp = await opportunities.get_or_404(session, args.opportunity_id)
        return f"Track {opp.title} in your applications?", {"opportunity_id": opp.id}
    if name == "add_todo":
        due = f" (due {human_day(args.due_date)})" if args.due_date else ""
        return f"Add “{args.title}” to your to-dos{due}?", args.model_dump(mode="json")
    raise NotFoundError("Unknown action")


def change_note(action):
    lines = []
    for field, value in action["changes"].items():
        label = field.replace("_", " ").capitalize()
        if field == "requirements" and value is not None:
            items = [
                f"{'Done' if item['done'] else 'Open'}: {item['label']}"
                for item in value
            ]
            value = "\n" + "\n".join(items) if items else "Empty checklist"
        elif value is None:
            value = "Clear date" if field == "deadline_date" else "No change"
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


def note(name, action):
    if name in edits.TOOLS:
        return edits.note(name, action)
    return change_note(action) if name == "update_application" else ""


async def apply_change(session, user_id, name, arguments):
    if name in edits.TOOLS:
        return await edits.apply(session, user_id, name, arguments)
    if name == "update_application":
        app = await applications.update_application(
            session,
            user_id,
            arguments["application_id"],
            ApplicationUpdate.model_validate(arguments["changes"]),
            commit=False,
        )
        return {
            "kind": "application",
            "id": app["id"],
            "title": app["title"],
            "detail": "Application details updated",
        }
    if name == "track_opportunity":
        app, created = await opportunities.track(
            session, user_id, arguments["opportunity_id"], commit=False
        )
        due = app["deadline_date"]
        return {
            "kind": "application",
            "id": app["id"],
            "title": app["title"],
            "detail": ", ".join(
                part
                for part in (app["organization"], due and f"Due {human_day(due)}")
                if part
            ),
            "already_tracked": not created,
        }
    if name == "add_todo":
        todo = await todos.create_todo(
            session, user_id, TodoCreate.model_validate(arguments), commit=False
        )
        due = todo["due_date"]
        return {
            "kind": "todo",
            "id": todo["id"],
            "title": todo["title"],
            "detail": f"Due {human_day(due)}" if due else "",
        }
    raise NotFoundError("Unknown action")
