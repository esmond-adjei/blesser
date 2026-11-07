"""Gradis conversation storage: the provider-format history, so later turns
see earlier tool results, and the human-readable transcript for the UI."""

import json

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant import models as assistant_models
from api.assistant import sources as gradis_sources
from api.core.db import like_pattern
from api.core.exceptions import BadRequestError, NotFoundError
from api.core.time import utcnow_naive


async def get_conversation_or_404(
    session: AsyncSession, conversation_id: str, user_id: str
) -> assistant_models.AssistantConversation:
    conv = (
        (
            await session.execute(
                select(assistant_models.AssistantConversation).where(
                    assistant_models.AssistantConversation.id == conversation_id,
                    assistant_models.AssistantConversation.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if conv is None:
        raise NotFoundError("Conversation not found")
    return conv


async def create_conversation(session: AsyncSession, user_id: str) -> dict:
    conv = assistant_models.AssistantConversation(user_id=user_id)
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return _conversation_out(conv, preview=None, message_count=0)


def _conversation_out(conv, preview: str | None, message_count: int) -> dict:
    return {
        "id": conv.id,
        "title": conv.title,
        "preview": preview,
        "message_count": message_count,
        "has_pending": conv.pending_call_json is not None,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
    }


async def list_conversations(
    session: AsyncSession,
    user_id: str,
    q: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Index newest first. `q` matches the title or any message body;
    `limit`/`offset` page it, no limit returns every chat."""
    Conv = assistant_models.AssistantConversation
    Msg = assistant_models.AssistantMessage
    stmt = select(Conv).where(Conv.user_id == user_id)
    term = (q or "").strip()
    if term:
        pattern = like_pattern(term)
        stmt = stmt.where(
            or_(
                Conv.title.ilike(pattern, escape="\\"),
                exists().where(
                    Msg.conversation_id == Conv.id,
                    Msg.content.ilike(pattern, escape="\\"),
                ),
            )
        )
    # The id breaks updated_at ties so pages never overlap.
    stmt = stmt.order_by(Conv.updated_at.desc(), Conv.id.desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    out = []
    for conv in rows:
        last = (
            await session.execute(
                select(assistant_models.AssistantMessage.content)
                .where(assistant_models.AssistantMessage.conversation_id == conv.id)
                .order_by(assistant_models.AssistantMessage.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        count = (
            await session.execute(
                select(func.count())
                .select_from(assistant_models.AssistantMessage)
                .where(assistant_models.AssistantMessage.conversation_id == conv.id)
            )
        ).scalar() or 0
        out.append(_conversation_out(conv, last, count))
    return out


def _turn_events(message: assistant_models.AssistantMessage) -> list[dict]:
    """The message's ordered turn log: the model's text and the tool calls
    it made, in the order they happened."""
    if not message.tool_calls_json:
        return []
    try:
        parsed = json.loads(message.tool_calls_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [e for e in parsed if isinstance(e, dict)]


async def get_messages(
    session: AsyncSession, user_id: str, conversation_id: str
) -> list[dict]:
    await get_conversation_or_404(session, conversation_id, user_id)
    rows = (
        (
            await session.execute(
                select(assistant_models.AssistantMessage)
                .where(
                    assistant_models.AssistantMessage.conversation_id == conversation_id,
                    assistant_models.AssistantMessage.user_id == user_id,
                )
                .order_by(assistant_models.AssistantMessage.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    out = []
    # Keys are per conversation: a reply can cite a source an earlier
    # turn looked up, so the registry grows message by message.
    registry = gradis_sources.SourceRegistry()
    for m in rows:
        events = _turn_events(m)
        if m.role == "user":
            out.append(
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at,
                    "tools": [],
                    "segments": [],
                    "mode": _user_mode(events),
                    "attachments": _user_attachments(events),
                    "context": _user_context(events),
                }
            )
            continue
        registry.absorb(events)
        # Legacy turns with no ordered log hold tool calls only.
        segments = events if any(e.get("kind") == "turn" for e in events) else []
        out.append(
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
                "model": m.model,
                "tools": [e for e in events if e.get("tool")],
                "segments": segments,
                "sources": registry.cited(m.content),
            }
        )
    return out


def _user_mode(events: list[dict]) -> str | None:
    """The mode a user turn ran in; None for turns sent before modes."""
    return next((e.get("mode") for e in events if e.get("kind") == "mode"), None)


def _user_attachments(events: list[dict]) -> list[dict]:
    return next((list(e.get("items") or []) for e in events if e.get("kind") == "attachments"), [])


def _user_context(events: list[dict]) -> list[dict]:
    return next((list(e.get("items") or []) for e in events if e.get("kind") == "context"), [])


async def source_registry(
    session: AsyncSession, conv: assistant_models.AssistantConversation
) -> gradis_sources.SourceRegistry:
    """Every source the conversation's stored turns have issued a key for."""
    rows = (
        (
            await session.execute(
                select(assistant_models.AssistantMessage)
                .where(
                    assistant_models.AssistantMessage.conversation_id == conv.id,
                    assistant_models.AssistantMessage.role == "assistant",
                )
                .order_by(assistant_models.AssistantMessage.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    registry = gradis_sources.SourceRegistry()
    for m in rows:
        registry.absorb(_turn_events(m))
    return registry


async def delete_conversation(
    session: AsyncSession, user_id: str, conversation_id: str
) -> dict:
    conv = await get_conversation_or_404(session, conversation_id, user_id)
    await session.delete(conv)
    await session.commit()
    return {"status": "deleted"}


async def rename_conversation(
    session: AsyncSession, user_id: str, conversation_id: str, title: str
) -> dict:
    """Rename a conversation; blank titles are refused. Auto-titling only
    applies while the title is still the default."""
    title = title.strip()
    if not title:
        raise BadRequestError("title must not be empty")
    conv = await get_conversation_or_404(session, conversation_id, user_id)
    conv.title = title[:80]
    await session.commit()
    return {"id": conv.id, "title": conv.title}


async def append_message(
    session: AsyncSession,
    conv: assistant_models.AssistantConversation,
    role: str,
    content: str,
    events: list[dict] | None = None,
    model: str | None = None,
) -> assistant_models.AssistantMessage:
    """Append one transcript message. `events` is an assistant turn's ordered
    log (text and tool calls); a user message's only entry is its mode."""
    if role not in ("user", "assistant"):
        raise BadRequestError("role must be 'user' or 'assistant'")
    msg = assistant_models.AssistantMessage(
        conversation_id=conv.id,
        user_id=conv.user_id,
        role=role,
        content=content,
        tool_calls_json=json.dumps(events or []),
        model=model,
        # Set here, not by the server default, so the message can be
        # serialized right away without a refresh.
        created_at=utcnow_naive(),
    )
    session.add(msg)
    if role == "user" and conv.title == "New Gradis chat" and content.strip():
        conv.title = content.strip()[:60]
    conv.updated_at = func.now()
    await session.flush()
    return msg


async def remove_from_message(
    session: AsyncSession,
    conv: assistant_models.AssistantConversation,
    message_id: str,
) -> int:
    """Drop one user message and every turn after it. Returns how many user
    messages preceded it, which locates the cut in the provider-format history."""
    rows = (
        (
            await session.execute(
                select(assistant_models.AssistantMessage)
                .where(
                    assistant_models.AssistantMessage.conversation_id == conv.id,
                    assistant_models.AssistantMessage.user_id == conv.user_id,
                )
                .order_by(assistant_models.AssistantMessage.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    index = next((i for i, m in enumerate(rows) if m.id == message_id), None)
    if index is None:
        raise NotFoundError("Message not found")
    if rows[index].role != "user":
        raise BadRequestError("Only a user message can be replaced")
    users_before = sum(1 for m in rows[:index] if m.role == "user")
    # The first prompt auto-names the chat; editing it should rename too,
    # unless the user gave the chat a custom title.
    first_user = next((m for m in rows if m.role == "user"), None)
    if (
        first_user is not None
        and first_user.id == message_id
        and conv.title == first_user.content.strip()[:60]
    ):
        conv.title = "New Gradis chat"
    await session.execute(
        delete(assistant_models.AssistantMessage).where(
            assistant_models.AssistantMessage.id.in_([m.id for m in rows[index:]])
        )
    )
    conv.updated_at = func.now()
    await session.flush()
    return users_before


def history_before_user(history: list[dict], users_before: int) -> list[dict]:
    """Cut history just before its (users_before + 1)-th user message; an
    empty prefix when the transcript outruns the history, rather than replay stale turns."""
    seen = 0
    for i, message in enumerate(history):
        if message.get("role") != "user":
            continue
        if seen == users_before:
            return history[:i]
        seen += 1
    return []


def load_history(conv: assistant_models.AssistantConversation) -> list[dict]:
    if not conv.history_json:
        return []
    try:
        parsed = json.loads(conv.history_json)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def save_history(
    conv: assistant_models.AssistantConversation, history: list[dict]
) -> None:
    conv.history_json = json.dumps(history, default=str)


def load_pending(conv: assistant_models.AssistantConversation) -> dict | None:
    if not conv.pending_call_json:
        return None
    try:
        parsed = json.loads(conv.pending_call_json)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def load_waiting(conv: assistant_models.AssistantConversation) -> dict | None:
    """The call still waiting for an answer, if any. An answered call stays
    on the conversation (so a dead turn can resume) but is not waiting."""
    pending = load_pending(conv)
    if pending is None:
        return None
    return pending if pending.get("status", "waiting") == "waiting" else None


def set_pending(
    conv: assistant_models.AssistantConversation,
    call: dict,
    history: list[dict],
) -> None:
    save_history(conv, history)
    conv.pending_call_json = json.dumps(call, default=str)


def answer_pending(
    conv: assistant_models.AssistantConversation,
    call: dict,
    history: list[dict],
    events: list[dict],
) -> None:
    """Record the user's answer, keeping the turn's log until the turn ends
    so a later failure continues the turn instead of restarting it."""
    save_history(conv, history)
    conv.pending_call_json = json.dumps(
        {**call, "status": "approved", "segments": events}, default=str
    )


def clear_pending(conv: assistant_models.AssistantConversation) -> None:
    conv.pending_call_json = None
