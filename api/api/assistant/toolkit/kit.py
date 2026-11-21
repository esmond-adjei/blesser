"""The Apply kit: profile, projects, documents and saved answers.

Contact details, identity numbers, birth details and references never reach the
model, in reads or in edits.
"""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, create_model
from sqlalchemy import select

from api.applicant_kit import models as kit_models
from api.applicant_kit import schemas as kit_schemas
from api.applicant_kit import service as kit
from api.core.exceptions import BadRequestError

from .base import (
    Applied,
    MemberLookup,
    Proposal,
    RecordId,
    Tool,
    ToolInput,
    bulk,
    field_lines,
    matching,
    preview,
    quoted,
    record,
)

#: Profile fields the Assistant may read and edit.
PROFILE_FIELDS = (
    "headline",
    "short_bio",
    "long_bio",
    "pronouns",
    "country_of_residence",
    "city",
    "education",
    "experience",
    "skills",
    "languages",
    "awards",
    "publications",
)
#: Project fields the Assistant may read and edit. Team details hold contact data.
PROJECT_FIELDS = (
    "name",
    "tagline",
    "stage",
    "sector",
    "country",
    "city",
    "problem",
    "solution",
    "target_customers",
    "market_size",
    "business_model",
    "competition",
    "traction",
    "impact",
    "why_now",
    "team_size",
    "women_led",
    "youth_led",
    "revenue_last_12_months",
    "funding_raised",
    "amount_sought",
    "currency",
    "use_of_funds",
)


def _optional(model, fields, name):
    return create_model(
        name,
        __base__=ToolInput,
        **{key: (model.model_fields[key].annotation | None, None) for key in fields},
    )


ProfileChanges = _optional(kit_schemas.ProfileIn, PROFILE_FIELDS, "ProfileChanges")
ProjectChanges = _optional(kit_schemas.ProjectIn, PROJECT_FIELDS, "ProjectChanges")
NewProject = create_model(
    "NewProject",
    __base__=ProjectChanges,
    name=(
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
        ],
        ...,
    ),
)


class KitLookup(MemberLookup):
    section: Literal["profile", "projects", "documents", "answers"]


class UpdateProfile(ToolInput):
    changes: ProfileChanges  # type: ignore[valid-type]


class ProjectId(ToolInput):
    project_id: RecordId


class UpdateProject(ProjectId):
    changes: ProjectChanges  # type: ignore[valid-type]


class AnswerId(ToolInput):
    answer_id: RecordId


class AddAnswer(ToolInput):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    answer: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50000)
    ]
    tags: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=30
    )
    project_id: RecordId | None = None


class AnswerChanges(ToolInput):
    question: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
        ]
        | None
    ) = None
    answer: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=50000),
        ]
        | None
    ) = None
    tags: (
        list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] | None
    ) = Field(default=None, max_length=30)


class UpdateAnswer(AnswerId):
    changes: AnswerChanges


class DocumentId(ToolInput):
    document_id: RecordId


class DocumentChanges(ToolInput):
    title: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
        ]
        | None
    ) = None
    kind: kit_schemas.Kind | None = None
    is_default: bool | None = None
    project_ids: list[RecordId] | None = Field(default=None, max_length=100)


class UpdateDocument(DocumentId):
    changes: DocumentChanges


def _changes(args):
    changes = args.changes.model_dump(
        mode="json", exclude_unset=True, exclude_none=True
    )
    if not changes:
        raise BadRequestError("Supply at least one change.")
    return changes


async def read_apply_kit(session, user_id, args, registry):
    if args.section == "profile":
        data = await session.scalar(
            select(kit_models.Profile.data).where(kit_models.Profile.user_id == user_id)
        )
        return {
            "profile": {
                key: value
                for key, value in record(data or {}, PROFILE_FIELDS).items()
                if kit.populated(value)
            },
            "scope": "Contact details, identity numbers, birth details and references are never shared with the Assistant.",
        }, None
    if args.section == "projects":
        rows = await kit.projects(session, user_id)
        fields = ("id", *PROJECT_FIELDS)
        kind, title_key = "project", "name"
    elif args.section == "documents":
        rows = await kit.documents(session, user_id)
        fields = ("id", "title", "kind", "is_default", "project_ids")
        kind, title_key = "document", "title"
    else:
        rows = await kit.answers(session, user_id, q=args.query)
        fields = ("id", "question", "answer", "tags", "project_id")
        kind, title_key = "answer", "question"
    search = tuple(f for f in fields if f != "id")
    matches = matching(rows, args.query, search) if args.section != "answers" else rows
    records = [
        {
            **record(row, fields),
            "source": registry.register(
                kind, row, title=row.get(title_key) or "Untitled"
            ),
        }
        for row in matches[:12]
    ]
    return {"items": records, "total": len(matches)}, len(matches)


async def propose_profile(session, user_id, args):
    changes = _changes(args)
    current = await kit.profile(session, user_id, reveal=True)
    kit_schemas.ProfileIn.model_validate({**current, **changes})
    return Proposal(
        "Update your Apply kit profile?",
        {"changes": changes},
        field_lines(_summaries(changes)),
    )


def _summaries(values):
    """Lists of records read better as a count on the card."""
    out = {}
    for key, value in values.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            names = [
                v.get("institution")
                or v.get("organization")
                or v.get("title")
                or v.get("language")
                or "Entry"
                for v in value
            ]
            out[key] = ", ".join(n for n in names if n)
        else:
            out[key] = value
    return out


async def apply_profile(session, user_id, arguments):
    current = await kit.profile(session, user_id, reveal=True)
    merged = {**current, **arguments["changes"]}
    req = kit_schemas.ProfileIn.model_validate(merged)
    await kit.profile(session, user_id, req)
    return Applied(
        {"updated": sorted(arguments["changes"])},
        "Updated your Apply kit profile.",
        preview("profile", "profile", "Your profile", "Apply kit"),
    )


async def propose_add_project(session, user_id, args):
    values = args.model_dump(mode="json", exclude_none=True)
    kit_schemas.ProjectIn.model_validate(values)
    return Proposal(
        f"Add the project {quoted(values['name'])} to your Apply kit?",
        values,
        field_lines({k: v for k, v in values.items() if k != "name"}),
    )


async def apply_add_project(session, user_id, arguments):
    row = await kit.save_project(
        session, user_id, kit_schemas.ProjectIn.model_validate(arguments)
    )
    return Applied(
        {"project_id": row["id"], "name": row["name"]},
        "Added the project to your Apply kit.",
        preview("project", row["id"], row["name"], row.get("tagline") or ""),
    )


async def _project(session, user_id, project_id):
    row = await kit.owned(session, kit_models.Project, user_id, project_id)
    return await kit.project_out(session, row)


async def propose_update_project(session, user_id, args):
    row = await _project(session, user_id, args.project_id)
    changes = _changes(args)
    kit_schemas.ProjectIn.model_validate({**row, **changes})
    return Proposal(
        f"Update the project {quoted(row['name'])}?",
        {"project_id": row["id"], "changes": changes},
        field_lines(changes),
    )


async def apply_update_project(session, user_id, arguments):
    current = await _project(session, user_id, arguments["project_id"])
    req = kit_schemas.ProjectIn.model_validate({**current, **arguments["changes"]})
    row = await kit.save_project(session, user_id, req, arguments["project_id"])
    return Applied(
        {"project_id": row["id"], "updated": sorted(arguments["changes"])},
        "Updated the project.",
        preview("project", row["id"], row["name"], row.get("tagline") or ""),
    )


async def propose_delete_project(session, user_id, args):
    row = await _project(session, user_id, args.project_id)
    return Proposal(
        f"Delete the project {quoted(row['name'])}?",
        {"project_id": row["id"]},
        "Documents linked to it stay in your Apply kit.",
        "Delete",
    )


async def apply_delete_project(session, user_id, arguments):
    await kit.delete_project(session, user_id, arguments["project_id"])
    return Applied({"deleted": True}, "Deleted the project.")


async def propose_add_answer(session, user_id, args):
    if args.project_id:
        await kit.owned(session, kit_models.Project, user_id, args.project_id)
    values = args.model_dump(mode="json", exclude_none=True)
    return Proposal(
        "Save this answer to your Apply kit?",
        values,
        field_lines(
            {
                "question": args.question,
                "answer": args.answer,
                **({"tags": args.tags} if args.tags else {}),
            }
        ),
    )


async def apply_add_answer(session, user_id, arguments):
    row = await kit.save_answer(
        session, user_id, kit_schemas.AnswerIn.model_validate(arguments)
    )
    return Applied(
        {"answer_id": row["id"]},
        "Saved the answer to your Apply kit.",
        preview("answer", row["id"], row["question"], f"{row['word_count']} words"),
    )


class AddAnswers(ToolInput):
    items: list[AddAnswer] = Field(min_length=1, max_length=10)


propose_add_answers, apply_add_answers = bulk(
    propose_add_answer, apply_add_answer, noun="answer", plural="answers"
)


async def _answer(session, user_id, answer_id):
    return kit.answer_out(
        await kit.owned(session, kit_models.Answer, user_id, answer_id)
    )


async def propose_update_answer(session, user_id, args):
    row = await _answer(session, user_id, args.answer_id)
    changes = _changes(args)
    return Proposal(
        f"Update your saved answer to {quoted(row['question'])}?",
        {"answer_id": row["id"], "changes": changes},
        field_lines(changes),
    )


async def apply_update_answer(session, user_id, arguments):
    current = await _answer(session, user_id, arguments["answer_id"])
    merged = {
        key: current[key] for key in ("question", "answer", "tags", "project_id")
    } | arguments["changes"]
    row = await kit.save_answer(
        session,
        user_id,
        kit_schemas.AnswerIn.model_validate(merged),
        arguments["answer_id"],
    )
    return Applied(
        {"answer_id": row["id"]},
        "Updated the saved answer.",
        preview("answer", row["id"], row["question"], f"{row['word_count']} words"),
    )


async def propose_delete_answer(session, user_id, args):
    row = await _answer(session, user_id, args.answer_id)
    return Proposal(
        f"Delete your saved answer to {quoted(row['question'])}?",
        {"answer_id": row["id"]},
        action="Delete",
    )


async def apply_delete_answer(session, user_id, arguments):
    await kit.delete_answer(session, user_id, arguments["answer_id"])
    return Applied({"deleted": True}, "Deleted the saved answer.")


async def _document(session, user_id, document_id):
    return await kit.owned(session, kit_models.Document, user_id, document_id)


async def propose_update_document(session, user_id, args):
    row = await _document(session, user_id, args.document_id)
    changes = _changes(args)
    if "project_ids" in changes:
        await kit.validate_ids(
            session, kit_models.Project, user_id, changes["project_ids"]
        )
    shown = dict(changes)
    if "kind" in shown:
        shown["kind"] = shown["kind"].replace("_", " ").capitalize()
    if "is_default" in shown:
        shown["is_default"] = "Yes" if shown["is_default"] else "No"
    if "project_ids" in shown:
        projects = {p["id"]: p["name"] for p in await kit.projects(session, user_id)}
        shown["project_ids"] = [projects.get(i, i) for i in shown["project_ids"]]
    return Proposal(
        f"Update the document {quoted(row.title)}?",
        {"document_id": row.id, "changes": changes},
        field_lines(
            shown, {"is_default": "Default for its kind", "project_ids": "Projects"}
        ),
    )


async def apply_update_document(session, user_id, arguments):
    row = await kit.patch_document(
        session,
        user_id,
        arguments["document_id"],
        kit_schemas.DocumentPatch.model_validate(arguments["changes"]),
    )
    return Applied(
        {"document_id": row["id"], "title": row["title"]},
        "Updated the document.",
        preview(
            "document",
            row["id"],
            row["title"],
            row["kind"].replace("_", " ").capitalize(),
        ),
    )


async def propose_delete_document(session, user_id, args):
    row = await _document(session, user_id, args.document_id)
    return Proposal(
        f"Delete the document {quoted(row.title)}?",
        {"document_id": row.id},
        f"File: {row.filename}\nThe file is removed from your Apply kit for good.",
        "Delete",
    )


async def apply_delete_document(session, user_id, arguments):
    await kit.delete_document(session, user_id, arguments["document_id"])
    return Applied({"deleted": True}, "Deleted the document.")


TOOLS = [
    Tool(
        "read_apply_kit",
        KitLookup,
        "Read one section of the member's Apply kit. Documents return metadata only. The profile excludes contact details and sensitive fields.",
        "Checked your Apply kit",
        "read",
        read=read_apply_kit,
    ),
    Tool(
        "update_profile",
        UpdateProfile,
        "Propose editing the member's Apply kit profile. Only supplied fields change. List fields such as education or skills replace the whole list, so read the profile first and keep existing entries. Contact and identity details can only be changed in the app.",
        "Update your profile",
        "change",
        propose=propose_profile,
        apply=apply_profile,
    ),
    Tool(
        "add_project",
        NewProject,
        "Propose adding a project or venture to the member's Apply kit.",
        "Add a project",
        "change",
        propose=propose_add_project,
        apply=apply_add_project,
    ),
    Tool(
        "update_project",
        UpdateProject,
        "Propose editing one of the member's Apply kit projects. Only supplied fields change.",
        "Update a project",
        "change",
        propose=propose_update_project,
        apply=apply_update_project,
    ),
    Tool(
        "delete_project",
        ProjectId,
        "Propose deleting one of the member's Apply kit projects.",
        "Delete a project",
        "delete",
        propose=propose_delete_project,
        apply=apply_delete_project,
    ),
    Tool(
        "add_answer",
        AddAnswer,
        "Propose saving an answer to a common application question in the member's Apply kit, optionally linked to a project.",
        "Save an answer",
        "change",
        propose=propose_add_answer,
        apply=apply_add_answer,
    ),
    Tool(
        "add_answers",
        AddAnswers,
        "Propose saving several answers to application questions in the member's Apply kit at once, up to ten. One approval covers them all. Use this instead of add_answer when there is more than one.",
        "Save answers",
        "change",
        propose=propose_add_answers,
        apply=apply_add_answers,
    ),
    Tool(
        "update_answer",
        UpdateAnswer,
        "Propose editing one of the member's saved answers. Only supplied fields change.",
        "Update a saved answer",
        "change",
        propose=propose_update_answer,
        apply=apply_update_answer,
    ),
    Tool(
        "delete_answer",
        AnswerId,
        "Propose deleting one of the member's saved answers.",
        "Delete a saved answer",
        "delete",
        propose=propose_delete_answer,
        apply=apply_delete_answer,
    ),
    Tool(
        "update_document",
        UpdateDocument,
        "Propose renaming a document, changing its kind, making it the default for its kind, or linking it to projects. Files can only be uploaded in the app.",
        "Update a document",
        "change",
        propose=propose_update_document,
        apply=apply_update_document,
    ),
    Tool(
        "delete_document",
        DocumentId,
        "Propose deleting a document and its file from the member's Apply kit.",
        "Delete a document",
        "delete",
        propose=propose_delete_document,
        apply=apply_delete_document,
    ),
]
