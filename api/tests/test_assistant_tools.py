"""The Assistant's tools across the app: reads, proposals, approved changes and ownership."""

import asyncio
import uuid
from datetime import date

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import select

from api.applicant_kit import models as kit_models
from api.applications.models import Application
from api.assistant import tools
from api.assistant.sources import SourceRegistry
from api.auth.models import User
from api.core import egress
from api.core.config import settings
from api.core.db import SessionLocal
from api.core.exceptions import (
    BadRequestError,
    DomainError,
    NotFoundError,
    RateLimitError,
)
from api.core.time import utcnow_naive
from api.notifications.models import Notification
from api.opportunities.models import Opportunity
from api.scans.models import Scan
from api.todos.models import Todo

PUBLIC = "93.184.216.34"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def public_dns(monkeypatch, tmp_path):
    async def resolve(host, port):
        if host.endswith(".internal"):
            return ["10.1.2.3"]
        if host.endswith(".example"):
            return [PUBLIC]
        raise OSError("no such host")

    monkeypatch.setattr(egress, "_resolve", resolve)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "secrets_key", Fernet.generate_key().decode())


def member():
    user_id = "tools-" + uuid.uuid4().hex[:10]

    async def go():
        async with SessionLocal() as session:
            session.add(
                User(
                    id=user_id,
                    email=f"{user_id}@example.com",
                    password_hash="x",
                    email_verified_at=utcnow_naive(),
                )
            )
            await session.commit()

    run(go())
    return user_id


def add(*rows):
    async def go():
        async with SessionLocal() as session:
            session.add_all(rows)
            await session.commit()
            return [getattr(row, "id", None) for row in rows]

    return run(go())


def read(user, name, /, **arguments):
    async def go():
        async with SessionLocal() as session:
            args = tools.TOOLS[name][0].model_validate(arguments)
            return await tools.read(session, user, name, args, SourceRegistry())

    return run(go())[0]


def propose(user, name, /, **arguments):
    async def go():
        async with SessionLocal() as session:
            args = tools.TOOLS[name][0].model_validate(arguments)
            return await tools.proposal(session, user, name, args)

    return run(go())


def approve(user, name, proposal):
    async def go():
        async with SessionLocal() as session:
            return await tools.apply_change(session, user, name, proposal.arguments)

    return run(go())


def change(user, name, /, **arguments):
    proposal = propose(user, name, **arguments)
    return proposal, approve(user, name, proposal)


def test_every_change_tool_has_a_label_a_proposal_and_an_apply_step():
    assert "enable_changes" not in tools.TOOLS
    for name in tools.WRITES:
        tool = tools.get(name)
        assert tool.propose and tool.apply, name
        assert tool.label, name
    for name in tools.DELETES:
        assert name.startswith(("delete_", "cancel_")), name
    for name, (schema, description) in tools.TOOLS.items():
        assert "—" not in description and "·" not in description, name
        schema.model_json_schema()


def test_scan_tools_start_stop_and_delete_a_scan_with_approval():
    user = member()
    assert read(user, "scan_allowance")["left_today"] >= 1
    proposal = propose(
        user,
        "start_scan",
        category="startup",
        region="Ghana",
        focus="Climate grants",
        sites=["grants.example"],
    )
    assert proposal.summary == "Start a scan for startup opportunities in Ghana?"
    assert proposal.action == "Start scan"
    assert "Sites: https://grants.example" in proposal.note
    assert not read(user, "list_scans")["items"]

    started = approve(user, "start_scan", proposal)
    scan_id = started.result["scan_id"]
    assert started.preview["kind"] == "scan"
    listed = read(user, "list_scans", query="ghana")
    assert [row["id"] for row in listed["items"]] == [scan_id]
    detail = read(user, "get_scan", scan_id=scan_id)
    assert detail["status"] == "running"
    assert detail["sites"] == ["https://grants.example"]

    stop = propose(user, "cancel_scan", scan_id=scan_id)
    assert stop.action == "Stop scan"
    assert approve(user, "cancel_scan", stop).result["status"] == "cancelled"
    with pytest.raises(BadRequestError):
        propose(user, "cancel_scan", scan_id=scan_id)

    delete = propose(user, "delete_scan", scan_id=scan_id)
    assert delete.action == "Delete"
    approve(user, "delete_scan", delete)
    assert not read(user, "list_scans")["items"]


def test_scan_proposals_check_sites_and_the_allowance(monkeypatch):
    user = member()
    with pytest.raises(BadRequestError):
        propose(user, "start_scan", category="research", sites=["admin.internal"])
    with pytest.raises(ValidationError):
        propose(user, "start_scan", category="research", sites=["a.example"] * 6)

    monkeypatch.setattr(settings, "rate_limits_enabled", True)
    add(
        *[
            Scan(user_id=user, region="Ghana", categories=["research"], status="done", kind="member")
            for _ in range(3)
        ]
    )
    allowance = read(user, "scan_allowance")
    assert allowance["left_this_hour"] == 0 and allowance["next_at"] is not None
    with pytest.raises(RateLimitError) as limit:
        propose(user, "start_scan", category="research")
    card = limit.value.card
    assert card["kind"] == "scan_limit" and card["title"] == "No scans left this hour"
    assert card["available_at"] == allowance["next_at"].isoformat()


def test_an_approved_scan_still_counts_against_the_limit(monkeypatch):
    user = member()
    proposal = propose(user, "start_scan", category="student")
    monkeypatch.setattr(settings, "rate_limits_enabled", True)
    add(
        *[
            Scan(user_id=user, region="Ghana", categories=["student"], status="done", kind="member")
            for _ in range(3)
        ]
    )
    with pytest.raises(RateLimitError):
        approve(user, "start_scan", proposal)


def test_scan_finds_can_be_read_and_tracked_by_their_owner_only():
    user, other = member(), member()
    [scan_id] = add(
        Scan(user_id=user, region="Ghana", categories=["startup"], status="done", kind="member")
    )
    [opp_id] = add(
        Opportunity(
            title="Find in review",
            organization="Fund",
            category="startup",
            kind="grant",
            status="in_review",
            source="agent",
            dedupe_key=uuid.uuid4().hex,
            scan_id=scan_id,
            deadline_date=date(2040, 3, 1),
        )
    )
    from api.scans.models import ScanFind

    add(ScanFind(scan_id=scan_id, opportunity_id=opp_id, created=True))
    detail = read(user, "get_scan", scan_id=scan_id)
    assert detail["finds"][0]["in_review"] is True
    assert detail["finds"][0]["deadline"] == "1 Mar 2040"
    with pytest.raises(NotFoundError):
        read(other, "get_scan", scan_id=scan_id)
    with pytest.raises(NotFoundError):
        propose(other, "track_opportunity", opportunity_id=opp_id)
    _, applied = change(user, "track_opportunity", opportunity_id=opp_id)
    assert applied.result["title"] == "Find in review"


def test_source_tools_add_update_check_and_remove_a_site():
    user, other = member(), member()
    proposal, added = change(
        user, "add_source", url="grants.example", category="research", note="PhD calls"
    )
    assert proposal.summary == "Add https://grants.example to your sources?"
    source_id = added.result["source_id"]
    assert read(user, "list_sources")["items"][0]["note"] == "PhD calls"
    with pytest.raises(BadRequestError):
        propose(user, "add_source", url="admin.internal", category="research")
    with pytest.raises(NotFoundError):
        propose(other, "update_source", source_id=source_id, changes={"paused": True})

    _, updated = change(
        user, "update_source", source_id=source_id, changes={"paused": True}
    )
    assert updated.result["paused"] is True
    with pytest.raises(BadRequestError):
        propose(user, "check_sources")
    change(user, "update_source", source_id=source_id, changes={"paused": False})
    check, started = change(user, "check_sources")
    assert "grants.example" in check.note
    assert len(started.result["scan_ids"]) == 1
    with pytest.raises(RateLimitError):
        approve(user, "check_sources", check)

    remove = propose(user, "delete_source", source_id=source_id)
    assert remove.action == "Delete"
    approve(user, "delete_source", remove)
    assert read(user, "list_sources")["items"] == []


def test_application_and_to_do_tools_cover_add_update_and_delete():
    user, other = member(), member()
    proposal, added = change(
        user,
        "add_application",
        title="Local fellowship",
        organization="City Fund",
        deadline_date="2040-05-02",
    )
    assert proposal.summary == "Add “Local fellowship” to your applications?"
    assert "Deadline date: 2 May 2040" in proposal.note
    app_id = added.result["application_id"]
    with pytest.raises(NotFoundError):
        propose(other, "delete_application", application_id=app_id)

    status, _ = change(
        user,
        "update_application",
        application_id=app_id,
        changes={"status": "rejected"},
    )
    assert status.note == "Status: Not this time"

    todo, made = change(
        user,
        "add_todo",
        title="Ask for a reference",
        due_date="2040-04-20",
        priority="high",
        application_id=app_id,
    )
    assert todo.summary.startswith(
        "Add “Ask for a reference” to your to-dos (due 20 Apr"
    )
    todo_id = made.result["todo_id"]
    listed = read(user, "list_todos")
    assert listed["items"][0]["id"] == todo_id
    assert listed["items"][0]["due"] == "20 Apr 2040"
    with pytest.raises(NotFoundError):
        propose(other, "update_todo", todo_id=todo_id, changes={"done": True})
    with pytest.raises(NotFoundError):
        propose(other, "add_todo", title="Sneaky", application_id=app_id)

    done, _ = change(user, "update_todo", todo_id=todo_id, changes={"done": True})
    assert done.summary == "Mark “Ask for a reference” as done?"
    assert read(user, "list_todos", status="done")["items"][0]["done"] is True
    moved, _ = change(user, "update_todo", todo_id=todo_id, changes={"due_date": None})
    assert moved.note == "Due date: Clear date"

    approve(user, "delete_todo", propose(user, "delete_todo", todo_id=todo_id))
    approve(
        user,
        "delete_application",
        propose(user, "delete_application", application_id=app_id),
    )
    assert read(user, "list_applications")["items"] == []
    assert read(user, "list_todos", status="all")["items"] == []


def test_profile_edits_never_touch_contact_or_identity_details():
    user = member()

    async def seed():
        from api.applicant_kit import schemas as kit_schemas
        from api.applicant_kit import service as kit

        async with SessionLocal() as session:
            await kit.profile(
                session,
                user,
                kit_schemas.ProfileIn(
                    email="me@example.com",
                    phone="+233 20 000 0000",
                    headline="Engineer",
                    skills=["Python"],
                    sensitive={"passport_number": "G1234567"},
                ),
            )

    run(seed())
    profile = read(user, "read_apply_kit", section="profile")["profile"]
    assert profile == {"headline": "Engineer", "skills": ["Python"]}
    with pytest.raises(ValidationError):
        propose(user, "update_profile", changes={"email": "new@example.com"})
    with pytest.raises(ValidationError):
        propose(user, "update_profile", changes={"short_bio": "x" * 301})

    proposal, _ = change(
        user,
        "update_profile",
        changes={"skills": ["Python", "Research"], "city": "Kumasi"},
    )
    assert "Skills: Python, Research" in proposal.note

    async def saved():
        from api.applicant_kit import service as kit

        async with SessionLocal() as session:
            return await kit.profile(session, user, reveal=True)

    after = run(saved())
    assert after["email"] == "me@example.com"
    assert after["phone"] == "+233 20 000 0000"
    assert after["sensitive"]["passport_number"] == "G1234567"
    assert after["city"] == "Kumasi"


def test_project_answer_and_document_tools_respect_ownership():
    user, other = member(), member()
    _, project = change(
        user, "add_project", name="Siwa", tagline="Clean water", stage="prototype"
    )
    project_id = project.result["project_id"]
    with pytest.raises(ValidationError):
        propose(user, "add_project", name="Bad", website_url="file:///etc/passwd")
    with pytest.raises(NotFoundError):
        propose(
            other, "update_project", project_id=project_id, changes={"stage": "growth"}
        )
    change(
        user, "update_project", project_id=project_id, changes={"traction": "40 pilots"}
    )
    projects = read(user, "read_apply_kit", section="projects")["items"]
    assert projects[0]["traction"] == "40 pilots"
    assert projects[0]["tagline"] == "Clean water"

    _, answer = change(
        user,
        "add_answer",
        question="Why you?",
        answer="I build water systems.",
        project_id=project_id,
    )
    answer_id = answer.result["answer_id"]
    with pytest.raises(NotFoundError):
        propose(other, "delete_answer", answer_id=answer_id)
    with pytest.raises(NotFoundError):
        propose(other, "add_answer", question="Q", answer="A", project_id=project_id)
    change(user, "update_answer", answer_id=answer_id, changes={"tags": ["motivation"]})
    saved = read(user, "read_apply_kit", section="answers")["items"][0]
    assert saved["tags"] == ["motivation"]
    assert saved["answer"] == "I build water systems."

    [doc_id] = add(
        kit_models.Document(
            id=uuid.uuid4().hex,
            user_id=user,
            kind="cv",
            title="Old CV",
            filename="cv.pdf",
            content_type="application/pdf",
            size_bytes=10,
            storage_key=f"{user}/missing.pdf",
        )
    )
    with pytest.raises(NotFoundError):
        propose(other, "update_document", document_id=doc_id, changes={"title": "Mine"})
    with pytest.raises(NotFoundError):
        propose(
            user,
            "update_document",
            document_id=doc_id,
            changes={"project_ids": ["nope"]},
        )
    renamed, _ = change(
        user,
        "update_document",
        document_id=doc_id,
        changes={"title": "CV 2026", "is_default": True, "project_ids": [project_id]},
    )
    assert "Projects: Siwa" in renamed.note
    docs = read(user, "read_apply_kit", section="documents")["items"]
    assert docs[0]["title"] == "CV 2026"
    assert docs[0]["project_ids"] == [project_id]

    approve(
        user, "delete_document", propose(user, "delete_document", document_id=doc_id)
    )
    approve(user, "delete_answer", propose(user, "delete_answer", answer_id=answer_id))
    approve(
        user, "delete_project", propose(user, "delete_project", project_id=project_id)
    )
    assert read(user, "read_apply_kit", section="projects")["items"] == []
    assert read(user, "read_apply_kit", section="documents")["items"] == []


def test_settings_tools_cover_matching_searches_notifications_and_name():
    user, other = member(), member()
    proposal, _ = change(
        user,
        "update_match_profile",
        changes={
            "categories": ["research"],
            "countries": ["Ghana"],
            "alerts": "weekly",
        },
    )
    assert "Alerts: Weekly" in proposal.note
    profile = read(user, "get_match_profile")
    assert profile["saved"] is True
    assert profile["categories"] == ["research"]
    assert profile["alerts"] == "weekly"
    read(user, "list_for_you")

    search, made = change(
        user,
        "add_saved_search",
        name="PhD grants",
        filters={"q": "phd", "category": "research"},
        alerts="daily",
    )
    assert "Finds: “phd”, Research" in search.note
    search_id = made.result["search_id"]
    with pytest.raises(NotFoundError):
        propose(other, "delete_saved_search", search_id=search_id)
    change(user, "update_saved_search", search_id=search_id, changes={"alerts": "off"})
    assert read(user, "list_saved_searches")["items"][0]["alerts"] == "off"
    approve(
        user,
        "delete_saved_search",
        propose(user, "delete_saved_search", search_id=search_id),
    )
    assert read(user, "list_saved_searches")["items"] == []

    notes, _ = change(
        user,
        "update_notification_settings",
        changes={
            "channels": [{"kind": "deadline", "channel": "email", "on": False}],
            "quiet_start": "22:00",
            "quiet_end": "07:00",
        },
    )
    assert "Application deadlines, Email: Off" in notes.note
    settings_out = read(user, "get_notification_settings")
    deadline = next(k for k in settings_out["kinds"] if k["kind"] == "deadline")
    assert deadline["channels"]["email"] is False
    assert settings_out["quiet_start"] == "22:00"
    with pytest.raises(ValidationError):
        propose(user, "update_notification_settings", changes={"quiet_start": "25:00"})

    add(
        Notification(
            user_id=user,
            kind="deadline",
            title="Due soon",
            body="",
            link="",
            dedupe_key=uuid.uuid4().hex,
        ),
        Notification(
            user_id=other,
            kind="deadline",
            title="Not yours",
            body="",
            link="",
            dedupe_key=uuid.uuid4().hex,
        ),
    )
    inbox = read(user, "list_notifications", unread_only=True)
    assert [row["title"] for row in inbox["items"]] == ["Due soon"]
    other_id = read(other, "list_notifications")["items"][0]["id"]
    with pytest.raises(NotFoundError):
        propose(user, "mark_notifications_read", notification_id=other_id)
    _, marked = change(user, "mark_notifications_read")
    assert marked.result["marked"] == 1
    with pytest.raises(BadRequestError):
        propose(user, "mark_notifications_read")
    assert read(other, "list_notifications")["unread"] == 1

    name, _ = change(user, "update_display_name", display_name="  Ama   Mensah ")
    assert name.summary == "Change your name to “Ama Mensah”?"
    with pytest.raises(BadRequestError):
        propose(user, "update_display_name", display_name="Ama Mensah")


def test_submitting_an_opportunity_goes_to_review():
    user = member()
    proposal = propose(
        user,
        "submit_opportunity",
        title=f"Makers Grant {uuid.uuid4().hex[:6]}",
        link="https://makers.example/grant",
        category="startup",
        kind="grant",
    )
    assert "reviews suggestions" in proposal.note
    with pytest.raises((ValueError, DomainError)):
        propose(
            user,
            "submit_opportunity",
            title="Bad link",
            link="javascript:alert(1)",
            category="startup",
        )
    applied = approve(user, "submit_opportunity", proposal)

    async def saved():
        async with SessionLocal() as session:
            return await session.get(Opportunity, applied.result["opportunity_id"])

    opp = run(saved())
    assert opp.created_by == user
    assert opp.source == "community"


def test_reads_of_another_members_records_are_not_found():
    user, other = member(), member()
    [app_id] = add(Application(user_id=other, title="Theirs"))
    [todo_id] = add(Todo(user_id=other, title="Theirs", position=1))
    with pytest.raises(NotFoundError):
        read(user, "get_application", application_id=app_id)
    assert read(user, "list_todos", status="all")["items"] == []
    with pytest.raises(NotFoundError):
        propose(user, "delete_todo", todo_id=todo_id)

    async def still_there():
        async with SessionLocal() as session:
            return await session.scalar(select(Todo.id).where(Todo.id == todo_id))

    assert run(still_there()) == todo_id


def test_bulk_tools_take_one_approval_for_many_items():
    user = member()
    proposal, applied = change(
        user,
        "add_sources",
        items=[
            {"url": "grants.example/a", "category": "research", "note": "PhD calls"},
            {"url": "funds.example", "category": "startup"},
        ],
    )
    assert proposal.summary == "Add 2 sources?"
    assert proposal.action == "Add 2"
    assert "1. Add https://grants.example/a to your sources" in proposal.note
    assert "2. Add https://funds.example to your sources" in proposal.note
    assert applied.result["added"] == 2 and applied.result["failed"] == []
    assert len(applied.previews) == 2
    assert len(read(user, "list_sources")["items"]) == 2

    _, todos = change(
        user, "add_todos", items=[{"title": "Draft essay"}, {"title": "Email referee"}]
    )
    assert todos.result["added"] == 2
    assert [card["title"] for card in todos.previews] == [
        "Draft essay",
        "Email referee",
    ]

    _, answers = change(
        user,
        "add_answers",
        items=[
            {"question": "Why this programme?", "answer": "Because."},
            {"question": "Biggest win?", "answer": "Shipped it."},
        ],
    )
    assert answers.result["added"] == 2


def test_bulk_tools_reject_a_bad_item_before_any_approval_and_report_partial_failures():
    user = member()
    with pytest.raises(BadRequestError):
        propose(
            user,
            "add_sources",
            items=[
                {"url": "grants.example", "category": "research"},
                {"url": "admin.internal", "category": "research"},
            ],
        )
    with pytest.raises(ValidationError):
        propose(user, "add_todos", items=[])
    first = propose(
        user, "add_sources", items=[{"url": "one.example", "category": "student"}]
    )
    approve(user, "add_sources", first)
    again = propose(
        user,
        "add_sources",
        items=[
            {"url": "one.example", "category": "student"},
            {"url": "two.example", "category": "student"},
        ],
    )
    applied = approve(user, "add_sources", again)
    assert applied.result["added"] == 1
    assert len(applied.result["failed"]) == 1
    assert "couldn't be added" in applied.receipt
