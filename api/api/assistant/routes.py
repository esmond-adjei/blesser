import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant import conversations, live, service
from api.assistant.models import AssistantConversation
from api.assistant.schemas import (
    ChatDetail,
    ChatOut,
    ChatRequest,
    ConfirmRequest,
    RenameRequest,
)
from api.auth.routes import get_current_user
from api.auth.schemas import UserOut
from api.core.db import get_session
from api.core.exceptions import ConflictError, NotFoundError
from api.core.ratelimit import rate_limit

router = APIRouter(prefix="/assistant/conversations", tags=["assistant"])


async def _sse(turn):
    async for event in turn.follow():
        name = event["event"]
        if name == "heartbeat":
            yield ": keep-alive\n\n"
            continue
        data = {key: value for key, value in event.items() if key != "event"}
        yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _response(turn):
    return StreamingResponse(
        _sse(turn),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("", response_model=ChatOut, status_code=201)
async def create_chat(
    session: AsyncSession = Depends(get_session),
    current: UserOut = Depends(get_current_user),
):
    chat = AssistantConversation(user_id=current.id, title=conversations.NEW_TITLE)
    session.add(chat)
    await session.commit()
    await session.refresh(chat)
    return conversations.chat_out(chat)


@router.get("", response_model=list[ChatOut])
async def list_chats(
    limit: int = Query(30, ge=1, le=60),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    current: UserOut = Depends(get_current_user),
):
    rows = await session.scalars(
        select(AssistantConversation)
        .where(AssistantConversation.user_id == current.id)
        .order_by(AssistantConversation.updated_at.desc(), AssistantConversation.id)
        .offset(offset)
        .limit(limit)
    )
    return [conversations.chat_out(chat) for chat in rows]


@router.get("/{chat_id}", response_model=ChatDetail)
async def get_chat(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    current: UserOut = Depends(get_current_user),
):
    chat = await conversations.owned(session, chat_id, current.id)
    rows = await conversations.messages(session, chat_id)
    return ChatDetail(**conversations.chat_out(chat).model_dump(), messages=rows)


@router.patch("/{chat_id}", response_model=ChatOut)
async def rename_chat(
    chat_id: str,
    req: RenameRequest,
    session: AsyncSession = Depends(get_session),
    current: UserOut = Depends(get_current_user),
):
    chat = await conversations.owned(session, chat_id, current.id, lock=True)
    chat.title = req.title
    await session.commit()
    await session.refresh(chat)
    return conversations.chat_out(chat)


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    current: UserOut = Depends(get_current_user),
):
    chat = await conversations.owned(session, chat_id, current.id, lock=True)
    if conversations.running(chat):
        raise ConflictError("Stop the current reply before deleting this chat.")
    await session.delete(chat)
    await session.commit()


@router.post("/{chat_id}/chat", dependencies=[Depends(rate_limit("assistant"))])
async def chat(
    chat_id: str,
    req: ChatRequest,
    session: AsyncSession = Depends(get_session),
    current: UserOut = Depends(get_current_user),
):
    await conversations.owned(session, chat_id, current.id)
    if not service.configured():
        raise HTTPException(503, "Assistant isn't set up yet")
    lease = await conversations.claim(session, chat_id, current.id)
    return _response(
        live.start(
            chat_id,
            current.id,
            service.chat_turn(chat_id, current.id, lease, req.content),
        )
    )


@router.post("/{chat_id}/confirm", dependencies=[Depends(rate_limit("assistant"))])
async def confirm(
    chat_id: str,
    req: ConfirmRequest,
    session: AsyncSession = Depends(get_session),
    current: UserOut = Depends(get_current_user),
):
    lease = await conversations.claim(session, chat_id, current.id, call_id=req.call_id)
    return _response(
        live.start(
            chat_id,
            current.id,
            service.confirm_turn(chat_id, current.id, lease, req.approved),
        )
    )


@router.get("/{chat_id}/live")
async def follow(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    current: UserOut = Depends(get_current_user),
):
    await conversations.owned(session, chat_id, current.id)
    await session.rollback()
    turn = live.get(chat_id, current.id)
    if not turn:
        raise NotFoundError("No live reply in this chat.")
    return _response(turn)


@router.post("/{chat_id}/stop")
async def stop(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    current: UserOut = Depends(get_current_user),
):
    await conversations.owned(session, chat_id, current.id)
    await session.rollback()
    return {"stopped": await live.stop(chat_id, current.id)}
