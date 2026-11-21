from datetime import timedelta

from sqlalchemy import delete, func, select, update

from api.assistant.models import AssistantConversation, AssistantMessage
from api.assistant.schemas import ChatOut, MessageOut, PendingCall
from api.core.db import SessionLocal
from api.core.exceptions import ConflictError, NotFoundError
from api.core.ids import new_id
from api.core.time import utcnow_naive

LEASE_TTL = timedelta(minutes=10)
NEW_TITLE = "New chat"


def running(chat):
    return bool(
        chat.turn_started_at and chat.turn_started_at > utcnow_naive() - LEASE_TTL
    )


def chat_out(chat):
    return ChatOut(
        id=chat.id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        running=running(chat),
        pending_call=PendingCall.model_validate(chat.pending) if chat.pending else None,
    )


async def owned(session, chat_id, user_id, *, lock=False):
    query = select(AssistantConversation).where(
        AssistantConversation.id == chat_id,
        AssistantConversation.user_id == user_id,
    )
    chat = await session.scalar(
        query.with_for_update().execution_options(populate_existing=True)
        if lock
        else query
    )
    if chat is None:
        raise NotFoundError("Chat not found")
    return chat


async def messages(session, chat_id, *, limit=None, before=None):
    query = select(AssistantMessage).where(AssistantMessage.conversation_id == chat_id)
    if before is not None:
        query = query.where(AssistantMessage.position < before)
    rows = list(
        await session.scalars(
            query.order_by(AssistantMessage.position.desc()).limit(limit)
        )
    )
    return [MessageOut.model_validate(row) for row in reversed(rows)]


async def append(
    session,
    chat,
    role,
    content,
    *,
    trace=None,
    sources=None,
    cited_deadlines=False,
    context=None,
):
    last = await session.scalar(
        select(func.max(AssistantMessage.position)).where(
            AssistantMessage.conversation_id == chat.id
        )
    )
    row = AssistantMessage(
        conversation_id=chat.id,
        position=(last or 0) + 1,
        role=role,
        content=content,
        trace=trace or [],
        sources=sources or [],
        cited_deadlines=cited_deadlines,
        context=context,
    )
    chat.updated_at = utcnow_naive()
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return MessageOut.model_validate(row)


async def last_question(session, chat_id):
    return await session.scalar(
        select(AssistantMessage)
        .where(
            AssistantMessage.conversation_id == chat_id,
            AssistantMessage.role == "user",
        )
        .order_by(AssistantMessage.position.desc())
        .limit(1)
    )


async def rewind(session, chat_id):
    """Drops everything after the last question; returns it and the messages before it."""
    last = await last_question(session, chat_id)
    if last is None:
        raise NotFoundError("There's no question to answer again.")
    await session.execute(
        delete(AssistantMessage).where(
            AssistantMessage.conversation_id == chat_id,
            AssistantMessage.position > last.position,
        )
    )
    previous = await messages(session, chat_id, limit=16, before=last.position)
    return MessageOut.model_validate(last), previous, last.context


async def claim(session, chat_id, user_id, *, call_id=None):
    chat = await owned(session, chat_id, user_id, lock=True)
    if running(chat):
        raise ConflictError("This chat is already working on a reply.")
    if call_id is not None and (not chat.pending or chat.pending["id"] != call_id):
        raise NotFoundError("This action is no longer waiting for confirmation.")
    if call_id is None and chat.pending:
        raise ConflictError("Approve or decline the pending action first.")
    chat.turn_id = new_id()
    chat.turn_started_at = utcnow_naive()
    lease = chat.turn_id
    await session.commit()
    return lease


async def held(session, chat_id, user_id, lease):
    chat = await owned(session, chat_id, user_id, lock=True)
    if chat.turn_id != lease:
        raise ConflictError("This turn is no longer active.")
    return chat


async def release(chat_id, lease):
    async with SessionLocal() as session:
        await session.execute(
            update(AssistantConversation)
            .where(
                AssistantConversation.id == chat_id,
                AssistantConversation.turn_id == lease,
            )
            .values(
                turn_id=None,
                turn_started_at=None,
                updated_at=AssistantConversation.updated_at,
            )
        )
        await session.commit()
