"""Applications and to-dos."""

from datetime import date
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints

from api.applications import service as applications
from api.applications.schemas import ApplicationCreate, ApplicationUpdate
from api.core.exceptions import BadRequestError
from api.core.time import human_day
from api.todos import service as todos
from api.todos.models import TodoPriority
from api.todos.schemas import TodoCreate, TodoUpdate

from .base import (
    Applied,
    MemberLookup,
    Proposal,
    RecordId,
    RequiredQuery,
    Tool,
    ToolInput,
    bulk,
    field_lines,
    matching,
    preview,
    quoted,
    record,
)


def status_label(status):
    return "Not this time" if status == "rejected" else str(status).capitalize()


class ApplicationLookup(ToolInput):
    application_id: RequiredQuery


class ApplicationChanges(ApplicationUpdate):
    model_config = ConfigDict(extra="forbid")


class UpdateApplication(ApplicationLookup):
    changes: ApplicationChanges


class AddApplication(ApplicationCreate):
    model_config = ConfigDict(extra="forbid")


class TodoLookup(MemberLookup):
    status: Literal["open", "done", "all"] = "open"


class TodoId(ToolInput):
    todo_id: RecordId


class AddTodo(ToolInput):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    due_date: date | None = None
    priority: TodoPriority | None = None
    notes: Annotated[str, StringConstraints(max_length=4000)] = ""
    application_id: RecordId | None = None


class TodoChanges(ToolInput):
    title: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
        ]
        | None
    ) = None
    notes: Annotated[str, StringConstraints(max_length=4000)] | None = None
    due_date: date | None = None
    priority: TodoPriority | None = None
    done: bool | None = None


class UpdateTodo(TodoId):
    changes: TodoChanges


def _app_detail(app):
    due = app["deadline_date"]
    return ", ".join(
        part
        for part in (app.get("organization"), due and f"Due {human_day(due)}")
        if part
    )


async def list_applications(session, user_id, args, registry):
    rows = await applications.list_applications(session, user_id)
    rows = matching(rows, args.query, ("title", "organization", "status"))
    records = []
    for row in rows[:16]:
        status = status_label(row["status"])
        key = registry.register("application", row, detail=status)
        records.append(
            {
                **record(
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
        "scope": "The authenticated member's saved applications. Status is application progress, not catalog moderation. Use id as application_id with get_application, update_application or delete_application. opportunity_id refers to a separate catalog record, which may be unavailable. Empty requirements mean no saved checklist, not that the opportunity has no requirements.",
    }, len(rows)


async def get_application(session, user_id, args, registry):
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


def change_note(changes):
    lines = []
    for field, value in changes.items():
        label = field.replace("_", " ").capitalize()
        if field == "requirements" and value is not None:
            items = [
                f"{'Done' if item['done'] else 'Open'}: {item['label']}"
                for item in value
            ]
            value = "\n" + "\n".join(items) if items else "Empty checklist"
        elif field == "status" and value is not None:
            value = status_label(value)
        elif value is None:
            value = "Clear date" if field.endswith("date") else "No change"
        elif field.endswith("date"):
            value = human_day(date.fromisoformat(value))
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


async def propose_update_application(session, user_id, args):
    app = await applications.get_or_404(session, user_id, args.application_id)
    patch = args.changes.model_dump(exclude_unset=True, mode="json")
    if not patch:
        raise ValueError("Supply at least one field to update.")
    return Proposal(
        f"Update “{app.title}”?",
        {"application_id": app.id, "changes": patch},
        change_note(patch),
    )


async def apply_update_application(session, user_id, arguments):
    app = await applications.update_application(
        session,
        user_id,
        arguments["application_id"],
        ApplicationUpdate.model_validate(arguments["changes"]),
    )
    return Applied(
        {"application_id": app["id"], "title": app["title"], "status": app["status"]},
        "Updated your application details.",
        preview("application", app["id"], app["title"], "Application details updated"),
    )


async def propose_add_application(session, user_id, args):
    values = args.model_dump(mode="json", exclude_defaults=True)
    shown = {k: v for k, v in values.items() if k != "title"}
    return Proposal(
        f"Add “{args.title}” to your applications?",
        values,
        change_note(shown),
    )


async def apply_add_application(session, user_id, arguments):
    app = await applications.create_application(
        session, user_id, ApplicationCreate.model_validate(arguments)
    )
    return Applied(
        {"application_id": app["id"], "title": app["title"]},
        "Added to your applications.",
        preview("application", app["id"], app["title"], _app_detail(app)),
    )


async def propose_delete_application(session, user_id, args):
    app = await applications.get_or_404(session, user_id, args.application_id)
    return Proposal(
        f"Delete “{app.title}” from your applications?",
        {"application_id": app.id},
        "Its checklist and notes are deleted too. To-dos linked to it stay.",
        "Delete",
    )


async def apply_delete_application(session, user_id, arguments):
    await applications.delete_application(session, user_id, arguments["application_id"])
    return Applied({"deleted": True}, "Deleted the application.")


async def list_todos(session, user_id, args, registry):
    rows = await todos.list_todos(session, user_id, status=args.status)
    rows = matching(
        rows, args.query, ("title", "opportunity_title", "application_label")
    )
    records = [
        {
            **record(row, ("id", "title", "done", "priority", "application_label")),
            "source": (
                key := registry.register(
                    "todo",
                    {**row, "deadline_date": row.get("due_date")},
                    detail="Done" if row["done"] else "Open",
                )
            ),
            "due": registry.deadlines.get(key),
        }
        for row in rows[:16]
    ]
    return {
        "items": records,
        "total": len(rows),
        "scope": "Use id as todo_id with update_todo or delete_todo.",
    }, len(rows)


def _todo_detail(todo):
    if todo["done"]:
        return "Done"
    return f"Due {human_day(todo['due_date'])}" if todo["due_date"] else ""


async def propose_add_todo(session, user_id, args):
    if args.application_id:
        await applications.get_or_404(session, user_id, args.application_id)
    due = f" (due {human_day(args.due_date)})" if args.due_date else ""
    values = args.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    values["title"] = args.title
    extra = {k: v for k, v in values.items() if k in ("priority", "notes")}
    return Proposal(
        f"Add “{args.title}” to your to-dos{due}?",
        values,
        field_lines(extra),
    )


async def apply_add_todo(session, user_id, arguments):
    todo = await todos.create_todo(
        session, user_id, TodoCreate.model_validate(arguments)
    )
    return Applied(
        {"todo_id": todo["id"], "title": todo["title"]},
        "Added to your to-dos.",
        preview("todo", todo["id"], todo["title"], _todo_detail(todo)),
    )


class AddTodos(ToolInput):
    items: list[AddTodo] = Field(min_length=1, max_length=15)


propose_add_todos, apply_add_todos = bulk(
    propose_add_todo, apply_add_todo, noun="to-do", plural="to-dos"
)


async def _todo(session, user_id, todo_id):
    return await todos._get_or_404(session, user_id, todo_id)


async def propose_update_todo(session, user_id, args):
    row = await _todo(session, user_id, args.todo_id)
    changes = args.changes.model_dump(mode="json", exclude_unset=True)
    if not changes:
        raise BadRequestError("Supply at least one change.")
    if changes.get("title") is None:
        changes.pop("title", None)
    if set(changes) == {"done"}:
        summary = (
            f"Mark {quoted(row.title)} as done?"
            if changes["done"]
            else f"Reopen {quoted(row.title)}?"
        )
        return Proposal(summary, {"todo_id": row.id, "changes": changes})
    shown = dict(changes)
    if "done" in shown:
        shown["done"] = "Done" if shown["done"] else "Open"
    return Proposal(
        f"Update the to-do {quoted(row.title)}?",
        {"todo_id": row.id, "changes": changes},
        change_note({("status" if k == "done" else k): v for k, v in shown.items()}),
    )


async def apply_update_todo(session, user_id, arguments):
    todo = await todos.update_todo(
        session,
        user_id,
        arguments["todo_id"],
        TodoUpdate.model_validate(arguments["changes"]),
    )
    return Applied(
        {"todo_id": todo["id"], "title": todo["title"], "done": todo["done"]},
        "Updated the to-do.",
        preview("todo", todo["id"], todo["title"], _todo_detail(todo)),
    )


async def propose_delete_todo(session, user_id, args):
    row = await _todo(session, user_id, args.todo_id)
    return Proposal(
        f"Delete the to-do {quoted(row.title)}?", {"todo_id": row.id}, action="Delete"
    )


async def apply_delete_todo(session, user_id, arguments):
    await todos.delete_todo(session, user_id, arguments["todo_id"])
    return Applied({"deleted": True}, "Deleted the to-do.")


TOOLS = [
    Tool(
        "list_applications",
        MemberLookup,
        "Read the current member's applications, optionally by title, organization or status.",
        "Checked your applications",
        "read",
        read=list_applications,
    ),
    Tool(
        "get_application",
        ApplicationLookup,
        "Read the authenticated member's saved application details by application_id, including notes, link, benefits and requirements. Saved details remain readable even when the linked catalog record is unavailable. This does not grant access to unpublished catalog content.",
        "Checked an application",
        "read",
        read=get_application,
    ),
    Tool(
        "add_application",
        AddApplication,
        "Propose adding an application by hand, for an opportunity that is not in the catalog. For catalog listings use track_opportunity instead.",
        "Add an application",
        "change",
        propose=propose_add_application,
        apply=apply_add_application,
    ),
    Tool(
        "update_application",
        UpdateApplication,
        "Propose editing the member's own application, including its status. Only supplied fields change. Requirements replace the entire checklist, so read the application first and preserve existing completion states.",
        "Update application",
        "change",
        propose=propose_update_application,
        apply=apply_update_application,
    ),
    Tool(
        "delete_application",
        ApplicationLookup,
        "Propose deleting one of the member's applications.",
        "Delete an application",
        "delete",
        propose=propose_delete_application,
        apply=apply_delete_application,
    ),
    Tool(
        "list_todos",
        TodoLookup,
        "Read the current member's to-dos, optionally by title and completion status.",
        "Checked your to-dos",
        "read",
        read=list_todos,
    ),
    Tool(
        "add_todos",
        AddTodos,
        "Propose adding several to-dos at once, up to fifteen. One approval covers them all. Use this instead of add_todo when there is more than one.",
        "Add to-dos",
        "change",
        propose=propose_add_todos,
        apply=apply_add_todos,
    ),
    Tool(
        "add_todo",
        AddTodo,
        "Propose adding a to-do with a title and an optional member-requested date, priority, notes or linked application.",
        "Add a to-do",
        "change",
        propose=propose_add_todo,
        apply=apply_add_todo,
    ),
    Tool(
        "update_todo",
        UpdateTodo,
        "Propose renaming, rescheduling, reprioritising, or marking a to-do done or open again. Only supplied fields change. A null due_date clears the date.",
        "Update a to-do",
        "change",
        propose=propose_update_todo,
        apply=apply_update_todo,
    ),
    Tool(
        "delete_todo",
        TodoId,
        "Propose deleting one of the member's to-dos.",
        "Delete a to-do",
        "delete",
        propose=propose_delete_todo,
        apply=apply_delete_todo,
    ),
]
