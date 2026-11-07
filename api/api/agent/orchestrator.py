"""The agent loop: call the model, run its tools, repeat until it stops or hits the turn cap."""

import asyncio
import contextvars
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable

from api.agent.llm.base import is_transient
from api.agent.llm.factory import get_provider
from api.agent.llm.slots import model_slot
from api.agent.tool_preview import preview as tool_preview
from api.agent.tools import TOOL_DEFINITIONS, ToolContext, dispatch_batch
from api.agent.untrusted import UNTRUSTED_CONTENT_RULE, wrap_tool_result
from api.agents import registry as agents_registry
from api.core.config import settings
from api.prospects import grounding

RESULT_PREVIEW_CHARS = 1000
THINKING_PREVIEW_CHARS = 2000

log = logging.getLogger(__name__)

#: Marks tasks parked for model allowance; resuming the run requeues them.
ALLOWANCE_PAUSE_PREFIX = "Paused: "


#: A tool result with this key ends the task as done.
TASK_COMPLETE_KEY = "task_complete"


class TaskHalted(Exception):
    """Raised at a turn boundary so a halted task stops spending at once."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


async def _halt_reason(ctx, task_type: str | None) -> str | None:
    """Why this task must stop now, or None; test doubles never halt."""
    if getattr(ctx, "session", None) is None or getattr(ctx, "run", None) is None:
        return None
    from api.agent.tools.dispatch import run_halted

    return await run_halted(ctx, task_type)


class ModelAllowanceRefused(Exception):
    """The spend gate refused the next model call; the queue parks the task rather than failing it."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# Events: {"turn", "kind": "turn", "note"} per model text, and
# {"turn", "tool", "input", "result", "result_preview", "ok"} per tool call.
# "result" is the full payload; persisting sinks should keep only the preview.
EventCallback = Callable[[dict], Awaitable[None]]

CheckpointCallback = Callable[[list[dict]], Awaitable[None]]

# Blunt, so even weak models course-correct instead of summarizing an empty task.
EMPTY_FINISH_NUDGE = (
    "You are trying to finish without saving anything, which means this "
    "task accomplished nothing. Do not write another summary yet - keep "
    "working: search, verify, and save results with your tools first."
)


CLOSING_FORMAT_BLOCK = (
    "\n\nClose your final summary with these four labeled lines "
    "(keep the labels exactly; write None where a section is empty):\n"
    "Findings: <key facts you learned>\n"
    "Saved: <records you saved with tools, or None>\n"
    "Skipped: <leads you checked but did not save, with why, or None>\n"
    "Next: <suggested follow-up, or None>"
)


def with_closing_format(user_message: str) -> str:
    if CLOSING_FORMAT_BLOCK in user_message:
        return user_message
    return user_message + CLOSING_FORMAT_BLOCK


def _compact_old_tool_results(
    messages: list[dict],
    current_turn: int,
    max_age_turns: int,
    block_turns: int | None = None,
) -> list[dict]:
    """Replace tool results older than max_age_turns with a marker, in a new list.

    The cutoff moves in blocks of `block_turns` so the prefix stays byte-identical for the prompt cache.
    """
    if max_age_turns < 1:
        return messages
    block = max(1, settings.compaction_block_turns if block_turns is None else block_turns)
    cutoff = ((current_turn - max_age_turns) // block) * block
    compacted = []
    for m in messages:
        if m.get("role") == "tool" and m.get("_turn", current_turn) <= cutoff:
            compacted.append(
                {
                    **m,
                    "content": f"[{m.get('name', 'tool')} result already used - omitted]",
                }
            )
        else:
            compacted.append(m)
    return compacted


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


def add_task_usage(usage: dict | None, turn: int | None = None) -> None:
    """`turn` is the absolute turn count, so a task that fails later still reports turns taken."""
    totals = task_usage.get()
    if totals is None:
        return
    if turn is not None:
        totals["turns"] = turn
    if not usage:
        return
    totals["input_tokens"] += usage.get("input_tokens", 0) or 0
    totals["output_tokens"] += usage.get("output_tokens", 0) or 0
    if usage.get("cache_read_tokens"):
        totals["cache_read_tokens"] = (
            totals.get("cache_read_tokens", 0) + usage["cache_read_tokens"]
        )


def add_task_time(model: float = 0.0, tool: float = 0.0) -> None:
    totals = task_usage.get()
    if totals is None:
        return
    if model:
        totals["model_seconds"] = totals.get("model_seconds", 0.0) + model
    if tool:
        totals["tool_seconds"] = totals.get("tool_seconds", 0.0) + tool


def note_task_model(provider) -> None:
    totals = task_usage.get()
    if totals is None:
        return
    totals["provider"] = getattr(provider, "name", None) or type(provider).__name__
    totals["model"] = getattr(provider, "model", None) or None


def set_task_path(path: str, reason: str | None = None) -> None:
    totals = task_usage.get()
    if totals is None:
        return
    totals["path"] = path
    totals["path_reason"] = reason


async def _chat_with_retry(provider, messages, system: str, tools, turn: int):
    """One model turn; transient failures retry LLM_TURN_RETRIES times with exponential backoff."""
    attempts = max(settings.llm_turn_retries, 0) + 1
    deadline = settings.llm_call_deadline_seconds
    for attempt in range(attempts):
        try:
            # Slot waits don't count against the deadline, so a busy local backend serves calls in turn.
            async with model_slot(provider):
                call = provider.chat(
                    messages=messages,
                    system=system,
                    tools=tools,
                    max_tokens=settings.llm_max_tokens,
                )
                if deadline <= 0:
                    return await call
                # Bounds the whole call: SDK timeouts and retries could hold a loop for minutes.
                try:
                    return await asyncio.wait_for(call, deadline)
                except TimeoutError as exc:
                    raise TimeoutError(
                        f"no model reply within {deadline:.0f}s"
                    ) from exc
        except Exception as exc:
            if attempt == attempts - 1 or not is_transient(exc):
                raise
            # Jittered so tasks that timed out together don't resend together.
            delay = (
                settings.llm_retry_backoff_seconds
                * (2**attempt)
                * random.uniform(0.5, 1.5)
            )
            log.warning(
                "model turn %s failed (%s); retry %s/%s in %.0fs",
                turn + 1,
                type(exc).__name__,
                attempt + 1,
                attempts - 1,
                delay,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


def _auto_summary(finished: list, note: str | None) -> str:
    """Closing summary for a deterministic finish, from the terminal tool calls that succeeded."""
    saved, skipped = [], []
    for tool_use, result in finished:
        args = tool_use.arguments or {}
        if tool_use.name == "confirm_no_match":
            skipped.append(str(args.get("reason") or "no match"))
            continue
        label = args.get("name") or tool_use.name
        score = (
            (result or {}).get("similarity_score") if isinstance(result, dict) else None
        )
        score = score if score is not None else args.get("similarity_score")
        saved.append(f"{label} (score {score})" if score is not None else str(label))
    findings = " ".join((note or "").split())[:300] or "See the tool log."
    return (
        f"Findings: {findings}\n"
        f"Saved: {'; '.join(saved) or 'None'}\n"
        f"Skipped: {'; '.join(skipped) or 'None'}\n"
        "Next: None"
    )


async def _reserve_call(user_id, llm_kwargs: dict, estimate: int):
    """(reservation, refusal text): the spend gate run atomically with a token reservation."""
    if user_id is None:
        return None, None
    from api.billing import service as billing
    from api.core.exceptions import ForbiddenError, UpgradeRequiredError

    try:
        return await billing.reserve_model_call(user_id, llm_kwargs, estimate), None
    except (ForbiddenError, UpgradeRequiredError) as exc:
        return None, exc.message


async def run_agent_task(
    system_prompt: str,
    user_message: str,
    ctx: ToolContext,
    on_event: EventCallback | None = None,
    resume_messages: list[dict] | None = None,
    on_checkpoint: CheckpointCallback | None = None,
    progress_tools: set[str] | None = None,
    task_type: str | None = None,
    finish_on: set[str] | None = None,
    only_tools: set[str] | None = None,
    max_turns: int | None = None,
    small_model: bool = False,
) -> dict:
    """Run one bounded agent task to completion.

    - resume_messages: a checkpoint to continue from; its turns count against the cap.
    - progress_tools: finishing without calling one is nudged back, up to max_empty_finish_nudges.
    - small_model: use LLM_SMALL_MODEL when on the system model and one is set.
    - finish_on: the task ends when one of these tools succeeds, without another model turn.
    """
    # Test doubles have no DB session, so they get the static tool list.
    session = getattr(ctx, "session", None)
    user_id = getattr(ctx, "user_id", None)
    if task_type is not None and session is not None:
        task_cfg = await agents_registry.task_state(session, user_id, task_type)
        if not task_cfg["enabled"]:
            return {
                "final_text": f"Task type {task_type} is disabled by the operator; nothing to do.",
                "tool_log": [],
                "turns": 0,
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "nudges": 0,
            }
    tools = (
        await agents_registry.worker_definitions(session, user_id, task_type)
        if session is not None
        else list(TOOL_DEFINITIONS)
    )
    # A custom flow can switch the step off, narrow tools or add instructions, never widen or bypass gates.
    from api.flows import service as flows

    flow_step = await flows.step_for(session, getattr(ctx, "run", None), task_type)
    if flow_step is not None:
        flow_name, step = flow_step
        if not step.get("enabled", True):
            label = flows.STEP_META.get(task_type, {}).get("label", task_type) # type: ignore
            return {
                "final_text": f"Skipped: step '{label}' is turned off in flow '{flow_name}'.",
                "tool_log": [],
                "turns": 0,
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "nudges": 0,
            }
        system_prompt, tools = flows.apply_step(flow_name, step, system_prompt, tools)
    if only_tools is not None:
        tools = [t for t in tools if t.get("name") in only_tools]
    # Dispatch refuses any tool the model wasn't offered.
    try:
        ctx.offered_tools = {t["name"] for t in tools if t.get("name")}
    except AttributeError:  # frozen test doubles
        pass
    system_prompt = f"{system_prompt}\n\n{UNTRUSTED_CONTENT_RULE}"
    from api.metering.service import metered
    from api.providers import service as providers_service

    run_provider = getattr(getattr(ctx, "run", None), "llm_provider", None)
    # A model switched off mid-run falls back to Auto rather than failing every task.
    llm_kwargs = await providers_service.resolve_llm_kwargs(
        session, user_id, run_provider, disabled_to_system=True
    )
    if small_model and not llm_kwargs and settings.llm_small_model.strip():
        llm_kwargs = {"model": settings.llm_small_model.strip()}
    provider = metered(get_provider(**llm_kwargs), user_id, "research") # type: ignore
    note_task_model(provider)
    messages: list[dict] = (
        list(resume_messages)
        if resume_messages is not None
        else [{"role": "user", "content": with_closing_format(user_message)}]
    )
    if resume_messages is not None and _missing_required_extras(provider, messages):
        # Replaying this history would 400, so restart fresh; re-saves dedup.
        print(
            "[worker] checkpoint predates thought-signature capture; "
            "restarting task fresh instead of resuming",
            flush=True,
        )
        messages = [{"role": "user", "content": with_closing_format(user_message)}]
    messages = grounding.restore_from_checkpoint(ctx, messages)
    if resume_messages is not None:
        counts: dict[str, int] = {}
        for m in messages:
            for tc in m.get("tool_calls") or []:
                counts[tc.get("name")] = counts.get(tc.get("name"), 0) + 1
        try:
            ctx.tool_call_counts = counts
        except AttributeError:  # frozen test doubles
            pass
    turns_used = sum(1 for m in messages if m.get("role") == "assistant")
    tool_log = []
    usage_in, usage_out = 0, 0
    progress_made = any(
        tc.get("name") in (progress_tools or set())
        for m in messages
        for tc in (m.get("tool_calls") or [])
    )
    nudges = 0
    from api.billing import service as billing

    turn_limit = max_turns or settings.max_agent_turns
    for turn in range(turns_used, turn_limit):
        halted = await _halt_reason(ctx, task_type)
        if halted:
            raise TaskHalted(halted)
        # Reserve this call's tokens so concurrent tasks can't all pass on one reading.
        call_messages = _compact_old_tool_results(
            messages, turn + 1, settings.max_tool_result_age_turns
        )
        reservation, refusal = await _reserve_call(
            user_id,
            llm_kwargs,
            billing.estimate_tokens(
                call_messages, system_prompt, settings.llm_max_tokens
            ),
        )
        if refusal is not None:
            raise ModelAllowanceRefused(refusal)
        if session is not None:
            # Don't sit idle in transaction during the model call, or the pool caps concurrency.
            # Safe: sessions don't expire on commit.
            await session.commit()
        started = time.perf_counter()
        try:
            response = await _chat_with_retry(
                provider, call_messages, system_prompt, tools, turn
            )
        finally:
            add_task_time(model=time.perf_counter() - started)
            await billing.release(reservation)
        usage_in += (response.usage or {}).get("input_tokens", 0)
        usage_out += (response.usage or {}).get("output_tokens", 0)
        add_task_usage(response.usage, turn + 1)
        if on_event is not None and (response.text or "").strip():
            text = response.text.strip()
            if len(text) > THINKING_PREVIEW_CHARS:
                text = text[:THINKING_PREVIEW_CHARS] + "..."
            await on_event(
                {"turn": turn + 1, "kind": "turn", "note": text, "tokens": usage_in + usage_out}
            )

        if not response.tool_calls:
            messages.append({"role": "assistant", "content": response.text})
            if (
                progress_tools
                and not progress_made
                and nudges < settings.max_empty_finish_nudges
            ):
                nudges += 1
                messages.append({"role": "user", "content": EMPTY_FINISH_NUDGE})
                continue
            return {
                "final_text": response.text,
                "tool_log": tool_log,
                "turns": turn + 1,
                "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
                "nudges": nudges,
            }

        messages.append(
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

        # Halted mid-answer: this turn isn't checkpointed, so a resume asks again.
        halted = await _halt_reason(ctx, task_type)
        if halted:
            raise TaskHalted(halted)

        # One batch: read-only tools run concurrently. It never raises; failures come back as results.
        started = time.perf_counter()
        results = await dispatch_batch(
            [(tc.name, tc.arguments) for tc in response.tool_calls], ctx, task_type
        )
        add_task_time(tool=time.perf_counter() - started)

        # Request order, not completion order, keeps the trace and replayed history deterministic.
        for tool_use, result in zip(response.tool_calls, results, strict=True):
            if progress_tools and tool_use.name in progress_tools:
                progress_made = True
            tool_log.append(
                {
                    "turn": turn + 1,
                    "tool": tool_use.name,
                    "input": tool_use.arguments,
                    "result": result,
                }
            )
            if on_event is not None:
                await on_event(
                    {
                        "turn": turn + 1,
                        "tool": tool_use.name,
                        "input": tool_use.arguments,
                        "result": result,
                        "result_preview": tool_preview(result, RESULT_PREVIEW_CHARS),
                        "tokens": usage_in + usage_out,
                        # A budget-complete refusal is the task finishing, not a failure.
                        "ok": not (isinstance(result, dict) and "error" in result)
                        or bool(isinstance(result, dict) and result.get(TASK_COMPLETE_KEY)),
                    }
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_use.id,
                    "name": tool_use.name,
                    "content": wrap_tool_result(
                        tool_use.name,
                        # Unescaped, so titles the model quotes back match.
                        json.dumps(result, default=str, ensure_ascii=False),
                    ),
                    "_turn": turn + 1,
                }
            )

        complete = next(
            (
                r[TASK_COMPLETE_KEY]
                for r in results
                if isinstance(r, dict) and r.get(TASK_COMPLETE_KEY)
            ),
            None,
        )
        if complete:
            return {
                "final_text": complete,
                "tool_log": tool_log,
                "turns": turn + 1,
                "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
                "nudges": nudges,
            }

        if finish_on:
            finished = [
                (tool_use, result)
                for tool_use, result in zip(response.tool_calls, results, strict=True)
                if tool_use.name in finish_on
                and not (isinstance(result, dict) and "error" in result)
            ]
            if finished:
                return {
                    "final_text": _auto_summary(finished, response.text),
                    "tool_log": tool_log,
                    "turns": turn + 1,
                    "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
                    "nudges": nudges,
                }

        if on_checkpoint is not None:
            # Compacted: the raw history grows quadratically. Grounding rides along for resumes.
            await on_checkpoint(
                grounding.attach_to_checkpoint(
                    ctx,
                    _compact_old_tool_results(
                        messages, turn + 1, settings.max_tool_result_age_turns
                    ),
                )
            )

        openalex_wait = getattr(ctx, "openalex_wait", None)
        if openalex_wait is not None:
            # OpenAlex is unusable: stop rather than spend turns on a professor that can't be verified.
            raise openalex_wait

    return {
        "final_text": "Hit max_agent_turns without the agent signaling completion.",
        "tool_log": tool_log,
        "turns": turn_limit,
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
        "nudges": nudges,
    }
