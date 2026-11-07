"""Gradis routes. Every turn streams through a conversation so write tools
can pause for the user's confirmation."""

import logging

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant import conversations as gradis_conversations
from api.assistant import live as gradis_live
from api.assistant import queue as assistant_queue
from api.assistant import schemas as assistant_schemas
from api.assistant import service as assistant_service
from api.assistant import tools as assistant_tools
from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.billing import service as billing
from api.core.db import get_session
from api.core.egress import public_error
from api.core.exceptions import NotFoundError
from api.core.ratelimit import rate_limit
from api.runs.service import SSE_HEADERS, SSE_RETRY_MS, sse_frame

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assistant"])


@router.get("/search")
async def global_search(
    q: str = Query(min_length=2, max_length=200),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    from api.assistant.search import search_everything
    from api.assistant.sources import search_sources

    results = await search_everything(session, current.id, q, limit=8)
    hits = search_sources(results)
    chats = await gradis_conversations.list_conversations(session, current.id, q)
    hits.extend({"kind": "chat", "id": c["id"], "title": c["title"],
                 "href": f"/chat/{c['id']}", "subtitle": (c["preview"] or "")[:160]}
                for c in chats[:8])
    return {"items": hits}


@router.get("/assistant/model-info")
async def model_info(
    provider: str | None = None,
    conversation_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    from api.assistant.capabilities import effort_levels
    from api.assistant.prompts import GRADIS_SYSTEM_PROMPT
    from api.providers.service import context_window_for, resolve_llm_kwargs

    config = await resolve_llm_kwargs(session, current.id, provider)
    from api.agent.llm.factory import get_provider
    active = get_provider(**config)
    history = []
    if conversation_id:
        conv = await gradis_conversations.get_conversation_or_404(session, conversation_id, current.id)
        history = gradis_conversations.load_history(conv)
    return {"provider": active.name, "model": active.model,
            "effort_levels": effort_levels(active.name, active.model),
            "context_window": await context_window_for(session, current.id, config),
            "input_tokens": billing.estimate_tokens(history, GRADIS_SYSTEM_PROMPT, 0),
            "estimated": True}


@router.post("/assistant/attachments", dependencies=[Depends(rate_limit("upload"))])
async def upload_attachment(
    file: UploadFile = File(...),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    from api.assistant.attachments import MAX_BYTES, read_attachment
    return await read_attachment(file.filename or "attachment.txt", await file.read(MAX_BYTES + 1))


@router.get("/assistant/tools")
async def list_tools():
    """Tool names Gradis can use, so the UI can show what it did."""
    return {
        "tools": [
            {"name": t["name"], "description": t.get("description", "")}
            for t in assistant_tools.ASSISTANT_DEFINITIONS
        ]
    }


def _turn_error(exc: Exception) -> dict:
    """The event a failed turn ends with. The full error goes to the server
    log: the stream answered 200 before the model was called."""
    logger.warning("Gradis turn failed", exc_info=exc)
    # Never echo str(exc): a user-chosen provider controls the body.
    return {"event": "error", "message": f"Gradis turn failed: {public_error(exc)}"}


async def _event_stream(generator):
    """Wrap the service's event dicts as SSE frames; a failed turn is a data
    event, not a broken stream. Never mutate events: followers share them."""
    yield f"retry: {SSE_RETRY_MS}\n\n"
    try:
        async for event in generator:
            payload = {k: v for k, v in event.items() if k != "event"}
            yield sse_frame(event["event"], payload)
    except Exception as exc:  # noqa: BLE001 - stream the failure, don't hang the UI
        error = _turn_error(exc)
        yield sse_frame("error", {"message": error["message"]})


def _live_response(conversation_id: str, user_id: str, generator) -> StreamingResponse:
    """Run the turn on its own (a reload must not cancel it) and stream
    its events to this request."""
    turn = gradis_live.start(conversation_id, user_id, generator, _turn_error)
    return StreamingResponse(
        _event_stream(turn.follow()),
        media_type="text/event-stream",
        headers=dict(SSE_HEADERS),
    )


@router.post(
    "/assistant/conversations", response_model=assistant_schemas.ConversationOut
)
async def create_conversation(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Start a new Gradis conversation."""
    return assistant_schemas.ConversationOut(
        **await gradis_conversations.create_conversation(session, current.id)
    )


@router.get("/assistant/conversations")
async def list_conversations(
    q: str | None = Query(default=None, max_length=200),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Conversation index, newest first; `q` filters by title or message,
    `limit`/`offset` page it."""
    return await gradis_conversations.list_conversations(
        session, current.id, q, limit, offset
    )


@router.get("/assistant/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Full transcript of one conversation, plus any outstanding confirm
    and the prompts waiting in the queue."""
    conv = await gradis_conversations.get_conversation_or_404(
        session, conversation_id, current.id
    )
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": await gradis_conversations.get_messages(
            session, current.id, conversation_id
        ),
        "pending_call": gradis_conversations.load_waiting(conv),
        "queue": await assistant_queue.list_items(session, conv),
        # A reply still being written: the client follows it (/live).
        "running": gradis_live.running(conv.id),
    }


@router.delete("/assistant/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Delete a conversation and its transcript."""
    return await gradis_conversations.delete_conversation(
        session, current.id, conversation_id
    )


@router.patch("/assistant/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    req: assistant_schemas.RenameRequest,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Rename a conversation from the session menu."""
    return await gradis_conversations.rename_conversation(
        session, current.id, conversation_id, req.title
    )


@router.post("/assistant/conversations/{conversation_id}/queue")
async def queue_prompt(
    conversation_id: str,
    req: assistant_schemas.QueuePrompt,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Queue a prompt while a turn runs; an urgent one goes to the running turn."""
    conv = await gradis_conversations.get_conversation_or_404(
        session, conversation_id, current.id
    )
    item = await assistant_queue.enqueue(
        session, conv, current.id, req.content.strip(), req.urgent
    )
    return item


@router.patch("/assistant/conversations/{conversation_id}/queue/{item_id}")
async def update_queued_prompt(
    conversation_id: str,
    item_id: str,
    req: assistant_schemas.QueueUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Hand a queued prompt to the running turn, or put it back in line."""
    conv = await gradis_conversations.get_conversation_or_404(
        session, conversation_id, current.id
    )
    item = await assistant_queue.set_urgent(session, conv, item_id, req.urgent)
    if item is None:
        raise NotFoundError("No such queued prompt")
    return item


@router.delete("/assistant/conversations/{conversation_id}/queue/{item_id}")
async def delete_queued_prompt(
    conversation_id: str,
    item_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Drop a queued prompt."""
    conv = await gradis_conversations.get_conversation_or_404(
        session, conversation_id, current.id
    )
    if not await assistant_queue.remove_item(session, conv, item_id):
        raise NotFoundError("No such queued prompt")
    return {"status": "deleted"}


@router.post("/assistant/conversations/{conversation_id}/chat", dependencies=[Depends(rate_limit("chat"))])
async def chat_stream(
    conversation_id: str,
    req: assistant_schemas.ChatStreamRequest,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Stream one user turn as SSE: status/token/tool events, an optional
    confirm_required pause for write tools, then message + done."""
    await billing.require_feature(session, current.id, "gradis_chat")
    await billing.check_quota(session, current.id, "model_tokens_per_month")
    from api.core.exceptions import ConflictError

    conv = await gradis_conversations.get_conversation_or_404(
        session, conversation_id, current.id
    )
    if gradis_conversations.load_waiting(conv) is not None:
        raise ConflictError("A confirmation is outstanding — approve or deny it first")
    # One turn at a time: the history has a single writer.
    if assistant_service.turn_running(conversation_id):
        raise ConflictError("This chat is already working on something")
    generator = assistant_service.begin_streaming_turn(
        current.id,
        conversation_id,
        req.content.strip(),
        req.context,
        req.model.provider if req.model else None,
        retry=req.retry,
        replace_message_id=req.replace_message_id,
        continue_turn=req.continue_turn,
        mode=req.mode,
        effort=req.model.effort if req.model else None,
    )
    return _live_response(conversation_id, current.id, generator)


@router.get("/assistant/conversations/{conversation_id}/live")
async def follow_turn(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Follow the chat's running turn after a reload: every event since
    it started, then the rest as they come. 404 when nothing is running."""
    await gradis_conversations.get_conversation_or_404(session, conversation_id, current.id)
    await session.close()
    turn = gradis_live.get(conversation_id)
    if turn is None or turn.user_id != current.id:
        raise NotFoundError("Nothing is running in this chat")
    return StreamingResponse(
        _event_stream(turn.follow()),
        media_type="text/event-stream",
        headers=dict(SSE_HEADERS),
    )


@router.post("/assistant/conversations/{conversation_id}/stop")
async def stop_turn(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Stop the chat's running turn."""
    await gradis_conversations.get_conversation_or_404(session, conversation_id, current.id)
    return {"stopped": await gradis_live.stop(conversation_id)}


@router.post("/assistant/conversations/{conversation_id}/confirm", dependencies=[Depends(rate_limit("chat"))])
async def confirm_stream(
    conversation_id: str,
    req: assistant_schemas.ConfirmRequest,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Resolve an outstanding write confirmation, then stream onward."""
    await billing.require_feature(session, current.id, "gradis_chat")
    await billing.check_quota(session, current.id, "model_tokens_per_month")

    conv = await gradis_conversations.get_conversation_or_404(
        session, conversation_id, current.id
    )
    pending = gradis_conversations.load_waiting(conv)
    if pending is None or pending.get("id") != req.call_id:
        raise NotFoundError("No matching confirmation is outstanding")
    generator = assistant_service.resume_streaming_turn(
        current.id,
        conversation_id,
        req.call_id,
        req.approved,
        req.context,
        req.model.provider if req.model else None,
        mode=req.mode,
        effort=req.model.effort if req.model else None,
    )
    return _live_response(conversation_id, current.id, generator)
