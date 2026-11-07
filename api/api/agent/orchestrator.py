"""The agent loop: call the model, run its tools, repeat until it stops or hits the turn cap."""

import asyncio
import contextvars
import json
import logging
import random
from collections.abc import Awaitable, Callable

from api.agent.llm.base import is_transient
from api.agent.llm.factory import get_provider
from api.agent.llm.slots import model_slot
from api.agent.tool_preview import preview as tool_preview
from api.agent.tools import TOOL_DEFINITIONS, ToolContext, dispatch_batch
from api.agent.untrusted import UNTRUSTED_CONTENT_RULE, wrap_tool_result
from api.core.config import settings

RESULT_PREVIEW_CHARS = 1000
THINKING_PREVIEW_CHARS = 2000

log = logging.getLogger(__name__)


class TaskHalted(Exception):
    """Raised at a turn boundary so a cancelled task stops spending at once."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# Events: {"turn", "kind": "turn", "note"} per model text, and
# {"turn", "tool", "input", "result", "result_preview", "ok"} per tool call.
# "result" is the full payload; persisting sinks keep only the preview.
EventCallback = Callable[[dict], Awaitable[None]]
CheckpointCallback = Callable[[list[dict]], Awaitable[None]]

# Blunt, so even weak models course-correct instead of summarizing an empty task.
EMPTY_FINISH_NUDGE = (
    "You are trying to finish without saving anything, which means this "
    "task accomplished nothing. Do not write another summary yet - keep "
    "working: search, verify, and save results with your tools first."
)

CLOSING_FORMAT_BLOCK = (
    "\n\nClose your final summary with these labeled lines "
    "(keep the labels exactly; write None where a section is empty):\n"
    "Saved: <records you saved with tools, or None>\n"
    "Skipped: <leads you checked but did not save, with why, or None>"
)


def with_closing_format(user_message: str) -> str:
    if CLOSING_FORMAT_BLOCK in user_message:
        return user_message
    return user_message + CLOSING_FORMAT_BLOCK


def compact_old_tool_results(
    messages: list[dict], current_turn: int, max_age_turns: int, block_turns: int | None = None
) -> list[dict]:
    """Replace tool results older than max_age_turns with a marker, in a new list.

    The cutoff moves in blocks of `block_turns` so the prefix stays byte-identical for the
    prompt cache.
    """
    if max_age_turns < 1:
        return messages
    block = max(1, settings.compaction_block_turns if block_turns is None else block_turns)
    cutoff = ((current_turn - max_age_turns) // block) * block
    return [
        {**m, "content": f"[{m.get('name', 'tool')} result already used - omitted]"}
        if m.get("role") == "tool" and m.get("_turn", current_turn) <= cutoff
        else m
        for m in messages
    ]


def _missing_required_extras(provider, messages: list[dict]) -> bool:
    """True when a signature-requiring backend would 400 on signature-less calls in the history."""
    if not getattr(provider, "requires_tool_call_extras", False):
        return False
    from api.agent.llm.base import foreign_extras

    return any(
        not foreign_extras(tc.get("extra_content"), getattr(provider, "name", ""))
        for m in messages
        for tc in (m.get("tool_calls") or [])
    )


#: Set per attempt so a failed or halted task's tokens still reach its row.
task_usage: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "task_usage", default=None
)


def _add_usage(usage: dict | None, turn: int) -> None:
    totals = task_usage.get()
    if totals is None:
        return
    totals["turns"] = turn
    if usage:
        totals["input_tokens"] += usage.get("input_tokens", 0) or 0
        totals["output_tokens"] += usage.get("output_tokens", 0) or 0


async def _chat_with_retry(provider, messages, system: str, tools, turn: int):
    """One model turn; transient failures retry LLM_TURN_RETRIES times with backoff."""
    attempts = max(settings.llm_turn_retries, 0) + 1
    deadline = settings.llm_call_deadline_seconds
    for attempt in range(attempts):
        try:
            # Slot waits don't count against the deadline.
            async with model_slot(provider):
                call = provider.chat(
                    messages=messages, system=system, tools=tools, max_tokens=settings.llm_max_tokens
                )
                if deadline <= 0:
                    return await call
                try:
                    return await asyncio.wait_for(call, deadline)
                except TimeoutError as exc:
                    raise TimeoutError(f"no model reply within {deadline:.0f}s") from exc
        except Exception as exc:
            if attempt == attempts - 1 or not is_transient(exc):
                raise
            # Jittered so tasks that timed out together don't resend together.
            delay = settings.llm_retry_backoff_seconds * (2**attempt) * random.uniform(0.5, 1.5)
            log.warning(
                "model turn %s failed (%s); retry %s/%s in %.0fs",
                turn + 1, type(exc).__name__, attempt + 1, attempts - 1, delay,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


async def _halt_reason(ctx) -> str | None:
    if getattr(ctx, "session", None) is None or getattr(ctx, "run", None) is None:
        return None
    from api.agent.tools.dispatch import run_halted

    return await run_halted(ctx)


def _result(text: str, turns: int, usage_in: int, usage_out: int, nudges: int) -> dict:
    return {
        "final_text": text,
        "turns": turns,
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
        "nudges": nudges,
    }


async def run_agent_task(
    system_prompt: str,
    user_message: str,
    ctx: ToolContext,
    *,
    tools: list[str] | None = None,
    on_event: EventCallback | None = None,
    resume_messages: list[dict] | None = None,
    on_checkpoint: CheckpointCallback | None = None,
    progress_tools: set[str] | None = None,
    max_turns: int | None = None,
) -> dict:
    """Run one bounded agent task to completion.

    - tools: names offered to the model (default: every tool); dispatch refuses the rest.
    - resume_messages: a checkpoint to continue from; its turns count against the cap.
    - progress_tools: finishing without calling one is nudged back, up to
      MAX_EMPTY_FINISH_NUDGES times.
    """
    definitions = [t for t in TOOL_DEFINITIONS if tools is None or t["name"] in tools]
    try:
        ctx.offered_tools = {t["name"] for t in definitions}
    except AttributeError:  # frozen test doubles
        pass
    system_prompt = f"{system_prompt}\n\n{UNTRUSTED_CONTENT_RULE}"
    provider = get_provider()
    session = getattr(ctx, "session", None)

    fresh = [{"role": "user", "content": with_closing_format(user_message)}]
    messages: list[dict] = list(resume_messages) if resume_messages is not None else fresh
    if resume_messages is not None and _missing_required_extras(provider, messages):
        # Replaying this history would 400, so restart fresh; re-saves dedupe.
        messages = fresh
    turns_used = sum(1 for m in messages if m.get("role") == "assistant")
    usage_in = usage_out = nudges = 0
    progress_made = any(
        tc.get("name") in (progress_tools or set())
        for m in messages
        for tc in (m.get("tool_calls") or [])
    )

    turn_limit = max_turns or settings.max_agent_turns
    for turn in range(turns_used, turn_limit):
        if halted := await _halt_reason(ctx):
            raise TaskHalted(halted)
        call_messages = compact_old_tool_results(messages, turn + 1, settings.max_tool_result_age_turns)
        if session is not None:
            # Don't sit idle in a transaction during the model call.
            await session.commit()
        response = await _chat_with_retry(provider, call_messages, system_prompt, definitions, turn)
        usage_in += (response.usage or {}).get("input_tokens", 0)
        usage_out += (response.usage or {}).get("output_tokens", 0)
        _add_usage(response.usage, turn + 1)
        if on_event is not None and (response.text or "").strip():
            text = response.text.strip()
            if len(text) > THINKING_PREVIEW_CHARS:
                text = text[:THINKING_PREVIEW_CHARS] + "..."
            await on_event({"turn": turn + 1, "kind": "turn", "note": text})

        if not response.tool_calls:
            messages.append({"role": "assistant", "content": response.text})
            if progress_tools and not progress_made and nudges < settings.max_empty_finish_nudges:
                nudges += 1
                messages.append({"role": "user", "content": EMPTY_FINISH_NUDGE})
                continue
            return _result(response.text, turn + 1, usage_in, usage_out, nudges)

        messages.append(
            {
                "role": "assistant",
                "content": response.text,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments, "extra_content": tc.extra_content}
                    for tc in response.tool_calls
                ],
            }
        )
        # Halted mid-answer: this turn isn't checkpointed, so a resume asks again.
        if halted := await _halt_reason(ctx):
            raise TaskHalted(halted)

        results = await dispatch_batch([(tc.name, tc.arguments) for tc in response.tool_calls], ctx)
        # Request order keeps the trace and replayed history deterministic.
        for tool_use, result in zip(response.tool_calls, results, strict=True):
            if progress_tools and tool_use.name in progress_tools:
                progress_made = True
            if on_event is not None:
                await on_event(
                    {
                        "turn": turn + 1,
                        "tool": tool_use.name,
                        "input": tool_use.arguments,
                        "result": result,
                        "result_preview": tool_preview(result, RESULT_PREVIEW_CHARS),
                        "ok": not (isinstance(result, dict) and "error" in result),
                    }
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_use.id,
                    "name": tool_use.name,
                    "content": wrap_tool_result(
                        tool_use.name, json.dumps(result, default=str, ensure_ascii=False)
                    ),
                    "_turn": turn + 1,
                }
            )

        if on_checkpoint is not None:
            # Compacted: the raw history grows quadratically.
            await on_checkpoint(
                compact_old_tool_results(messages, turn + 1, settings.max_tool_result_age_turns)
            )

    return _result(
        "Hit the turn limit before the agent finished.", turn_limit, usage_in, usage_out, nudges
    )


__all__ = ["TaskHalted", "run_agent_task", "task_usage"]
