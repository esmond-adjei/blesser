"""Edits the assistant can propose beyond tracking: profile, projects, answers, documents, to-dos."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, create_model

from api.applicant_kit import models as kit_models
from api.applicant_kit import schemas as kit_schemas
from api.applicant_kit import service as kit
from api.applications import service as applications
from api.core.exceptions import NotFoundError
from api.todos import service as todos
from api.todos.models import TodoPriority
from api.todos.schemas import TodoUpdate

RequiredId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _optional(name: str, base: type[BaseModel], exclude=()):
    """A copy of `base` where every field may be left out."""
    fields = {}
    for key, info in base.model_fields.items():
        if key in exclude:
            continue
        kind = (
            Annotated[(info.annotation, *info.metadata)]
            if info.metadata
            else info.annotation
        )
        fields[key] = (kind | None, None)
    return create_model(name, __base__=ToolInput, **fields)


ProfileChanges = _optional(
    "ProfileChanges", kit_schemas.ProfileIn, exclude=("sensitive",)
)
ProjectChanges = _optional("ProjectChanges", kit_schemas.ProjectIn)
AnswerChanges = _optional("AnswerChanges", kit_schemas.AnswerIn)


class UpdateProfile(ToolInput):
    changes: ProfileChanges


class AddProject(kit_schemas.ProjectIn):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UpdateProject(ToolInput):
    project_id: RequiredId
    changes: ProjectChanges


class DeleteProject(ToolInput):
    project_id: RequiredId


class AddAnswer(kit_schemas.AnswerIn):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UpdateAnswer(ToolInput):
    answer_id: RequiredId
    changes: AnswerChanges


class DeleteAnswer(ToolInput):
    answer_id: RequiredId


class UpdateDocument(ToolInput):
    document_id: RequiredId
    changes: kit_schemas.DocumentPatch


class DeleteDocument(ToolInput):
    document_id: RequiredId


class TodoChanges(ToolInput):
    title: Annotated[str, Field(min_length=1, max_length=300)] | None = None
    notes: Annotated[str, Field(max_length=4000)] | None = None
    due_date: date | None = None
    priority: TodoPriority | None = None
    done: bool | None = None


class UpdateTodo(ToolInput):
    todo_id: RequiredId
    changes: TodoChanges


class DeleteTodo(ToolInput):
    todo_id: RequiredId


class DeleteApplication(ToolInput):
    application_id: RequiredId


TOOLS = {
    "update_profile": (
        UpdateProfile,
        "Propose editing the member's apply kit profile. Only supplied fields change; lists such as skills, education or experience replace the whole list, so read the profile first and keep what is there. Cannot touch ID numbers or other sensitive fields. Requires member approval.",
    ),
    "add_project": (
        AddProject,
        "Propose adding a project to the member's apply kit. Requires member approval.",
    ),
    "update_project": (
        UpdateProject,
        "Propose editing a project in the apply kit by project_id from read_apply_kit. Only supplied fields change. Requires member approval.",
    ),
    "delete_project": (
        DeleteProject,
        "Propose deleting a project from the apply kit by project_id. Requires member approval.",
    ),
    "add_answer": (
        AddAnswer,
        "Propose saving a reusable question and answer to the apply kit. Requires member approval.",
    ),
    "update_answer": (
        UpdateAnswer,
        "Propose editing a saved answer by answer_id from read_apply_kit. Only supplied fields change. Requires member approval.",
    ),
    "delete_answer": (
        DeleteAnswer,
        "Propose deleting a saved answer by answer_id. Requires member approval.",
    ),
    "update_document": (
        UpdateDocument,
        "Propose renaming a kit document, changing its kind, default flag or linked projects, by document_id from read_apply_kit. Cannot upload files. Requires member approval.",
    ),
    "delete_document": (
        DeleteDocument,
        "Propose deleting an uploaded kit document by document_id. Requires member approval.",
    ),
    "update_todo": (
        UpdateTodo,
        "Propose editing a to-do or marking it done, by todo_id from list_todos. Only supplied fields change. Requires member approval.",
    ),
    "delete_todo": (
        DeleteTodo,
        "Propose deleting a to-do by todo_id. Requires member approval.",
    ),
    "delete_application": (
        DeleteApplication,
        "Propose removing a saved application by application_id. Requires member approval.",
    ),
}

LABELS = {
    "update_profile": "Update profile",
    "add_project": "Add project",
    "update_project": "Update project",
    "delete_project": "Delete project",
    "add_answer": "Save answer",
    "update_answer": "Update answer",
    "delete_answer": "Delete answer",
    "update_document": "Update document",
    "delete_document": "Delete document",
    "update_todo": "Update to-do",
    "delete_todo": "Delete to-do",
    "delete_application": "Remove application",
}

FINAL = "This can't be undone."


def _names(patch: dict) -> str:
    return ", ".join(key.replace("_", " ") for key in patch)


async def _merged_profile(session, user_id, patch):
    row = await session.get(kit_models.Profile, user_id)
    base = {**(row.data if row else {}), "sensitive": (row.sensitive if row else {})}
    return kit_schemas.ProfileIn.model_validate({**base, **patch})


async def _merged_project(session, user_id, project_id, patch):
    row = await kit.owned(session, kit_models.Project, user_id, project_id)
    current = await kit.project_out(session, row)
    return row, kit_schemas.ProjectIn.model_validate({**current, **patch})


async def proposal(session, user_id, name, args):
    if name == "update_profile":
        patch = args.changes.model_dump(exclude_unset=True, mode="json")
        if not patch:
            raise ValueError("Supply at least one field to update.")
        await _merged_profile(session, user_id, patch)
        return f"Update your profile ({_names(patch)})?", {"changes": patch}
    if name == "add_project":
        data = args.model_dump(mode="json")
        return f"Add the project “{args.name}” to your apply kit?", data
    if name == "update_project":
        patch = args.changes.model_dump(exclude_unset=True, mode="json")
        if not patch:
            raise ValueError("Supply at least one field to update.")
        row, _ = await _merged_project(session, user_id, args.project_id, patch)
        title = row.data.get("name") or "this project"
        return f"Update the project “{title}” ({_names(patch)})?", {
            "project_id": row.id,
            "changes": patch,
        }
    if name == "delete_project":
        row = await kit.owned(session, kit_models.Project, user_id, args.project_id)
        return f"Delete the project “{row.data.get('name') or 'Untitled'}”? {FINAL}", {
            "project_id": row.id
        }
    if name == "add_answer":
        return f"Save an answer to “{args.question[:80]}”?", args.model_dump(
            mode="json"
        )
    if name == "update_answer":
        patch = args.changes.model_dump(exclude_unset=True, mode="json")
        if not patch:
            raise ValueError("Supply at least one field to update.")
        row = await kit.owned(session, kit_models.Answer, user_id, args.answer_id)
        return f"Update your answer to “{row.question[:80]}” ({_names(patch)})?", {
            "answer_id": row.id,
            "changes": patch,
        }
    if name == "delete_answer":
        row = await kit.owned(session, kit_models.Answer, user_id, args.answer_id)
        return f"Delete your answer to “{row.question[:80]}”? {FINAL}", {
            "answer_id": row.id
        }
    if name == "update_document":
        patch = args.changes.model_dump(exclude_unset=True, mode="json")
        if not patch:
            raise ValueError("Supply at least one field to update.")
        row = await kit.owned(session, kit_models.Document, user_id, args.document_id)
        return f"Update the document “{row.title}” ({_names(patch)})?", {
            "document_id": row.id,
            "changes": patch,
        }
    if name == "delete_document":
        row = await kit.owned(session, kit_models.Document, user_id, args.document_id)
        return f"Delete the document “{row.title}”? {FINAL}", {"document_id": row.id}
    if name == "update_todo":
        patch = args.changes.model_dump(exclude_unset=True, mode="json")
        if not patch:
            raise ValueError("Supply at least one field to update.")
        row = await todos._get_or_404(session, user_id, args.todo_id)
        return f"Update the to-do “{row.title}” ({_names(patch)})?", {
            "todo_id": row.id,
            "changes": patch,
        }
    if name == "delete_todo":
        row = await todos._get_or_404(session, user_id, args.todo_id)
        return f"Delete the to-do “{row.title}”? {FINAL}", {"todo_id": row.id}
    if name == "delete_application":
        app = await applications.get_or_404(session, user_id, args.application_id)
        return f"Remove “{app.title}” from your applications? {FINAL}", {
            "application_id": app.id
        }
    raise NotFoundError("Unknown action")


def note(name, action) -> str:
    """The changes a member is asked to approve, one per line."""
    if "changes" in action:
        return "\n".join(
            f"{key.replace('_', ' ').capitalize()}: {_show(value)}"
            for key, value in action["changes"].items()
        )
    if name in {"add_project", "add_answer"}:
        shown = (
            ("name", "tagline", "stage", "sector")
            if name == "add_project"
            else ("question", "answer")
        )
        return "\n".join(
            f"{key.capitalize()}: {_show(action[key])}"
            for key in shown
            if action.get(key)
        )
    return ""


def _show(value) -> str:
    if value is None or value == "":
        return "Clear"
    if isinstance(value, list):
        if not value:
            return "Empty list"
        return "; ".join(_show(item) for item in value)[:400]
    if isinstance(value, dict):
        return ", ".join(f"{_show(v)}" for v in value.values() if v)[:200]
    return str(value)[:400]


async def apply(session, user_id, name, arguments):
    if name == "update_profile":
        await kit.profile(session, user_id)
        req = await _merged_profile(session, user_id, arguments["changes"])
        await kit.profile(session, user_id, req)
        return {"receipt": "Updated your profile."}
    if name == "add_project":
        row = await kit.save_project(
            session, user_id, kit_schemas.ProjectIn.model_validate(arguments)
        )
        return {
            "kind": "project",
            "id": row["id"],
            "title": row["name"],
            "detail": row.get("tagline", ""),
            "receipt": "Added to your apply kit.",
        }
    if name == "update_project":
        _, req = await _merged_project(
            session, user_id, arguments["project_id"], arguments["changes"]
        )
        row = await kit.save_project(session, user_id, req, arguments["project_id"])
        return {
            "kind": "project",
            "id": row["id"],
            "title": row["name"],
            "detail": row.get("tagline", ""),
            "receipt": "Updated the project.",
        }
    if name == "delete_project":
        await kit.delete_project(session, user_id, arguments["project_id"])
        return {"receipt": "Deleted the project."}
    if name == "add_answer":
        row = await kit.save_answer(
            session, user_id, kit_schemas.AnswerIn.model_validate(arguments)
        )
        return {
            "kind": "answer",
            "id": row["id"],
            "title": row["question"],
            "detail": "",
            "receipt": "Saved to your apply kit.",
        }
    if name == "update_answer":
        existing = await kit.owned(
            session, kit_models.Answer, user_id, arguments["answer_id"]
        )
        current = kit.answer_out(existing)
        req = kit_schemas.AnswerIn.model_validate({**current, **arguments["changes"]})
        row = await kit.save_answer(session, user_id, req, arguments["answer_id"])
        return {
            "kind": "answer",
            "id": row["id"],
            "title": row["question"],
            "detail": "",
            "receipt": "Updated the answer.",
        }
    if name == "delete_answer":
        await kit.delete_answer(session, user_id, arguments["answer_id"])
        return {"receipt": "Deleted the answer."}
    if name == "update_document":
        row = await kit.patch_document(
            session,
            user_id,
            arguments["document_id"],
            kit_schemas.DocumentPatch.model_validate(arguments["changes"]),
        )
        return {
            "kind": "document",
            "id": row["id"],
            "title": row["title"],
            "detail": row["kind"].replace("_", " ").capitalize(),
            "receipt": "Updated the document.",
        }
    if name == "delete_document":
        await kit.delete_document(session, user_id, arguments["document_id"])
        return {"receipt": "Deleted the document."}
    if name == "update_todo":
        row = await todos.update_todo(
            session,
            user_id,
            arguments["todo_id"],
            TodoUpdate.model_validate(arguments["changes"]),
        )
        return {
            "kind": "todo",
            "id": row["id"],
            "title": row["title"],
            "detail": "Done" if row["done"] else "Open",
            "receipt": "Updated your to-do.",
        }
    if name == "delete_todo":
        await todos.delete_todo(session, user_id, arguments["todo_id"])
        return {"receipt": "Deleted the to-do."}
    if name == "delete_application":
        await applications.delete_application(
            session, user_id, arguments["application_id"]
        )
        return {"receipt": "Removed the application."}
    raise NotFoundError("Unknown action")
