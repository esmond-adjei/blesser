"""Gradis's prompt queue: what the student typed while a turn ran.

Taking a prompt removes it in the caller's transaction, so a turn that
dies before it commits leaves the prompt queued.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant import models as assistant_models


def _out(item: assistant_models.AssistantQueueItem) -> dict:
    return {
        "id": item.id,
        "content": item.content,
        "urgent": bool(item.urgent),
        "created_at": item.created_at,
    }


async def enqueue(
    session: AsyncSession,
    conv: assistant_models.AssistantConversation,
    user_id: str,
    content: str,
    urgent: bool = False,
) -> dict:
    """Park a prompt until the agent is ready for it."""
    item = assistant_models.AssistantQueueItem(
        conversation_id=conv.id,
        user_id=user_id,
        content=content,
        urgent=urgent,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return _out(item)


async def list_items(
    session: AsyncSession, conv: assistant_models.AssistantConversation
) -> list[dict]:
    """The waiting prompts, oldest first."""
    rows = (
        (
            await session.execute(
                select(assistant_models.AssistantQueueItem)
                .where(
                    assistant_models.AssistantQueueItem.conversation_id == conv.id
                )
                .order_by(assistant_models.AssistantQueueItem.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [_out(r) for r in rows]


async def remove_item(
    session: AsyncSession,
    conv: assistant_models.AssistantConversation,
    item_id: str,
) -> bool:
    """Drop one queued prompt. False when it is not this conversation's."""
    item = (
        (
            await session.execute(
                select(assistant_models.AssistantQueueItem).where(
                    assistant_models.AssistantQueueItem.id == item_id,
                    assistant_models.AssistantQueueItem.conversation_id == conv.id,
                )
            )
        )
        .scalars()
        .first()
    )
    if item is None:
        return False
    await session.delete(item)
    await session.commit()
    return True


async def set_urgent(
    session: AsyncSession,
    conv: assistant_models.AssistantConversation,
    item_id: str,
    urgent: bool,
) -> dict | None:
    """Hand a queued prompt to the running turn, or put it back in line."""
    item = (
        (
            await session.execute(
                select(assistant_models.AssistantQueueItem).where(
                    assistant_models.AssistantQueueItem.id == item_id,
                    assistant_models.AssistantQueueItem.conversation_id == conv.id,
                )
            )
        )
        .scalars()
        .first()
    )
    if item is None:
        return None
    item.urgent = urgent
    await session.commit()
    return _out(item)


async def take_urgent(
    session: AsyncSession, conv: assistant_models.AssistantConversation
) -> list[dict]:
    """The urgent prompts, oldest first, out of the queue."""
    rows = (
        (
            await session.execute(
                select(assistant_models.AssistantQueueItem)
                .where(
                    assistant_models.AssistantQueueItem.conversation_id == conv.id,
                    assistant_models.AssistantQueueItem.urgent.is_(True),
                )
                .order_by(assistant_models.AssistantQueueItem.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        await session.delete(row)
    if rows:
        await session.flush()
    return [_out(r) for r in rows]


async def take_next(
    session: AsyncSession, conv: assistant_models.AssistantConversation
) -> dict | None:
    """The next prompt to answer, out of the queue."""
    row = (
        (
            await session.execute(
                select(assistant_models.AssistantQueueItem)
                .where(assistant_models.AssistantQueueItem.conversation_id == conv.id)
                .order_by(assistant_models.AssistantQueueItem.created_at.asc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    await session.delete(row)
    await session.flush()
    return _out(row)
