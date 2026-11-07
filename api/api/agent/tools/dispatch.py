"""Route each agent tool call to its feature owner. Nothing here sends email: sending is manual.

A new tool needs a HANDLERS row and a definition in definitions.py (parity is tested).
"""

import asyncio
import json

import httpx

from api.agent import gates
from api.agent.tools.context import ToolContext
from api.agents import registry as agents_registry
from api.applications import tools as application_tools
from api.billing import service as billing
from api.candidates import tools as candidate_tools
from api.core.config import settings
from api.outreach import tools as outreach_tools
from api.prospects import grounding, openalex, sources, web
from api.prospects import tools as prospect_tools

__all__ = ["HANDLERS", "READ_ONLY_TOOLS", "ToolContext", "dispatch", "dispatch_batch"]


async def _search_web(tool_input: dict, ctx: ToolContext) -> dict:
    reused = web.reusable_search(tool_input["query"])
    if reused is not None:
        # No provider call, so no search quota.
        return {"results": web.brief_results(reused)}
    refusal = await billing.tool_call_refusal(
        ctx.user_id, "search", settings.search_provider
    )
    if refusal is not None:
        return {"error": refusal}
    results = await web.search_web(tool_input["query"])
    return {"results": web.brief_results(results)}


async def _fetch_page(tool_input: dict, ctx: ToolContext) -> dict:
    text = await web.fetch_page(
        tool_input["url"],
        max_chars=settings.fetch_max_chars,
        offset=tool_input.get("offset") or 0,
    )
    return {"text": text}


async def _openalex_call(tool: str, tool_input: dict, ctx: ToolContext, call):
    """The lookup's result, or an error dict for the tool to return.

    A lookup that already failed in this task isn't resent. In a task that waits out the
    daily budget, hitting it marks the task to wait. Other failures raise OpenAlexUnavailable.
    """
    key = tool + json.dumps(tool_input, sort_keys=True, default=str)
    failed = getattr(ctx, "failed_openalex_calls", None)
    if failed is not None and key in failed:
        call.close()  # never awaited
        return {
            "error": (
                f"This exact call already failed in this task ({failed[key]}); it is not "
                "sent again. Don't invent papers: save the professor with unverified: true "
                "and say their publications couldn't be checked, or conclude."
            )
        }
    try:
        return await call
    except openalex.OpenAlexWait as exc:
        if getattr(ctx, "park_on_openalex_budget", False):
            ctx.openalex_wait = exc
            return {"error": f"{exc.resumed_note}. It is available again: call {tool} again."}
        if failed is not None:
            failed[key] = str(exc).split(". ")[0]
        raise
    except openalex.OpenAlexUnavailable as exc:
        if failed is not None:
            failed[key] = str(exc).split(".")[0]
        raise
    except httpx.HTTPStatusError as exc:
        if failed is not None:
            failed[key] = f"HTTP {exc.response.status_code}"
        raise


async def _find_openalex_author(tool_input: dict, ctx: ToolContext) -> dict:
    # Scope to the school: a common name's right person is often not in the global top 5.
    institution_id = None
    school, school_names = None, []
    program = getattr(ctx, "program", None)
    session = getattr(ctx, "session", None)
    if program is not None and session is not None:
        from api.prospects import institutions
        from api.prospects import models as prospect_models

        school = await session.get(prospect_models.School, program.school_id)
        institution_id, school_names = await institutions.resolve_school(session, school)
    name = tool_input["name"]
    if school is not None:
        # An id the school's own page links comes first.
        linked = await sources.faculty_page_candidates(ctx, school, name)
        if linked:
            return {"candidates": sources.record(ctx, linked)}
    extra = {"institution_id": institution_id} if institution_id else {}
    try:
        candidates = await _openalex_call(
            "find_openalex_author",
            tool_input,
            ctx,
            openalex.find_author(name, tool_input.get("institution_hint"), **extra),
        )
    except openalex.OpenAlexUnavailable:
        grounding.record_openalex_outcome(ctx, grounding.UNAVAILABLE)
        found = await _other_sources(ctx, school, name, school_names)
        if found is None:
            raise
        return found
    if isinstance(candidates, dict):
        # OpenAlex is waiting or already failed this call: another source may still verify them.
        found = await _other_sources(ctx, school, name, school_names)
        if found is None:
            return candidates
        ctx.openalex_wait = None
        return found
    grounding.record_author_candidates(ctx, candidates)
    if not candidates:
        grounding.record_openalex_outcome(ctx, grounding.NOT_FOUND)
    if school is not None and not any(
        grounding.at_school(c, school.name, institution_id, school_names) for c in candidates
    ):
        found = await _other_sources(ctx, school, name, school_names)
        if found is not None:
            return {**found, "candidates": [*candidates, *found["candidates"]]}
    return {"candidates": candidates}


async def _other_sources(ctx, school, name: str, school_names) -> dict | None:
    """DBLP / NIH / NSF candidates at the school, recorded for grounding; None when none found."""
    if school is None or not sources.stands_in_for_openalex():
        return None
    found = await sources.fallback_candidates(ctx, school, name, school_names)
    if not found:
        return None
    shown = sources.record(ctx, found)
    return {"candidates": shown, "note": sources.note_for(shown)}


async def _get_author_works(tool_input: dict, ctx: ToolContext) -> dict:
    if grounding.is_source_id(tool_input["openalex_id"]):
        # Another source's author: their works came with the lookup.
        works = grounding.works_for(ctx, tool_input["openalex_id"])
        if not works:
            return {
                "error": (
                    "No fetched works for this openalex_id in this task: call "
                    "find_openalex_author again to look the professor up."
                )
            }
        return {"works": works if tool_input.get("full") else openalex.brief_works(works)}
    try:
        works = await _openalex_call(
            "get_author_works",
            tool_input,
            ctx,
            openalex.get_recent_works(tool_input["openalex_id"]),
        )
    except openalex.OpenAlexUnavailable:
        grounding.record_openalex_outcome(ctx, grounding.UNAVAILABLE)
        raise
    if isinstance(works, dict):
        return works
    grounding.record_works(ctx, tool_input["openalex_id"], works)
    if not works:
        grounding.record_openalex_outcome(ctx, grounding.NO_WORKS, tool_input["openalex_id"])
    # Full works are recorded for saving; the model reads brief ones unless it asks.
    if not tool_input.get("full"):
        works = openalex.brief_works(works)
    return {"works": works}


async def _confirm_no_match(tool_input: dict, ctx: ToolContext) -> dict:
    # Counts as progress so the empty-finish nudge doesn't tax legitimate "no match" outcomes.
    return {
        "acknowledged": True,
        "reason": tool_input.get("reason", ""),
        "reason_code": gates.no_match_reason(tool_input),
    }


HANDLERS = {
    "search_web": _search_web,
    "fetch_page": _fetch_page,
    "find_openalex_author": _find_openalex_author,
    "get_author_works": _get_author_works,
    "score_alignment": candidate_tools.handle_score_alignment,
    "save_program": prospect_tools.handle_save_program,
    "save_professor_record": prospect_tools.handle_save_professor_record,
    "save_email_draft": outreach_tools.handle_save_email_draft,
    "save_application": application_tools.handle_save_application,
    "confirm_no_match": _confirm_no_match,
    "spawn_professor_research": prospect_tools.handle_spawn_professor_research,
}


#: Safe to run concurrently: they never touch the AsyncSession (not concurrency-safe) or the save
#: counters, only plain dict writes for grounding. Everything else runs serially, in order.
READ_ONLY_TOOLS = frozenset(
    {
        "search_web",
        "fetch_page",
        "find_openalex_author",
        "get_author_works",
        "confirm_no_match",
    }
)

#: Refusing confirm_no_match on a halted run would leave no way to record a negative conclusion.
_HALT_EXEMPT = frozenset({"confirm_no_match"})


async def run_halted(ctx: ToolContext, task_type: str | None = None) -> str | None:
    """Why this task must stop: its run, agent or own attempt was halted or superseded."""
    from api.runs import agents
    from api.runs.queue import current_lease_halt

    await ctx.session.refresh(ctx.run, attribute_names=["status", "agent_states"])
    status = ctx.run.status
    if status in ("cancelled", "paused") and task_type not in agents.OUTLIVES_RUN_HALT:
        return status
    agent_state = agents.agent_states(ctx.run).get(task_type or "")
    if agent_state:
        return f"agent {agent_state}"
    task_halt = await current_lease_halt(ctx.session)
    return f"task {task_halt}" if task_halt else None


def _halted_error(halted: str) -> dict:
    if halted.startswith("agent "):
        return {
            "error": (
                f"This agent was {halted[6:]} for the run - its tools are refused; "
                "write your final summary instead."
            )
        }
    if halted.startswith("task "):
        return {
            "error": (
                f"This task was {halted[5:]} - its tools are refused; "
                "write your final summary instead."
            )
        }
    return {
        "error": (
            f"Run {halted} - work on halted runs is refused; "
            "write your final summary instead."
        )
    }


async def _invoke(
    tool_name: str,
    tool_input: dict,
    ctx: ToolContext,
    halted,
    states: dict[str, dict] | None = None,
    allowed: list[str] | None = None,
) -> dict:
    """One tool call; a refusal comes back tagged with its gate code."""
    return gates.with_gate(
        await _invoke_untagged(tool_name, tool_input, ctx, halted, states, allowed)
    )


async def _invoke_untagged(
    tool_name: str,
    tool_input: dict,
    ctx: ToolContext,
    halted,
    states: dict[str, dict] | None = None,
    allowed: list[str] | None = None,
) -> dict:
    """Never raises: inside a gather an exception would also discard its siblings' work."""
    if halted is not None and tool_name not in _HALT_EXEMPT:
        return _halted_error(halted)
    if states is not None:
        state = states.get(tool_name)
        if state is not None and not state["enabled"]:
            return {
                "error": (
                    f"Tool {tool_name} is disabled by the operator; "
                    "work without it or write your final summary instead."
                )
            }
    if allowed is not None and tool_name not in allowed:
        return {
            "error": (
                f"Tool {tool_name} is outside this task's allowlist; "
                "work without it or write your final summary instead."
            )
        }
    handler = HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return await handler(tool_input, ctx)
    except Exception as exc:  # noqa: BLE001 - surface to the agent, don't kill the task
        return {"error": f"{tool_name} failed: {exc}"}


def _is_read_only(tool_name: str, states: dict[str, dict] | None) -> bool:
    return tool_name in READ_ONLY_TOOLS


async def dispatch(tool_name: str, tool_input: dict, ctx: ToolContext) -> dict:
    """Single tool call, halt-checked; the agent loop uses dispatch_batch."""
    halted = None
    if tool_name not in _HALT_EXEMPT:
        halted = await run_halted(ctx)
        if halted:
            return gates.with_gate(_halted_error(halted))
    session = getattr(ctx, "session", None)
    user_id = getattr(ctx, "user_id", None)
    states = (
        await agents_registry.tool_states(
            session, user_id, agents_registry.WORKER_SCOPE, [tool_name]
        )
        if session is not None
        else None
    )
    handler = HANDLERS.get(tool_name)
    if handler is None:
        return gates.with_gate({"error": f"Unknown tool: {tool_name}"})
    return await _invoke(tool_name, tool_input, ctx, halted, states)


CAPPED_TASK_TYPE = "research_one_professor"
#: Tools whose failed calls _openalex_call already remembers.
_OPENALEX_TOOLS = frozenset({"find_openalex_author", "get_author_works"})


def _task_store(ctx, name: str) -> dict | None:
    """A per-task dict on the context; None on a frozen test double."""
    value = getattr(ctx, name, None)
    if value is None:
        value = {}
        try:
            setattr(ctx, name, value)
        except AttributeError:
            return None
    return value


def _call_key(name: str, args: dict) -> str:
    return name + json.dumps(args, sort_keys=True, default=str)


def _over_cap(name: str, ctx, task_type: str | None) -> dict | None:
    """Refusal past NARROW_TOOL_CAPS; counts the call otherwise."""
    if task_type != CAPPED_TASK_TYPE:
        return None
    cap = settings.narrow_tool_caps.get(name)
    counts = _task_store(ctx, "tool_call_counts")
    if cap is None or counts is None:
        return None
    if counts.get(name, 0) >= cap:
        return {
            "error": (
                f"Tool call limit: {name} was already called {cap} times in this task, the "
                "most allowed. Work from what you have: save the professor, save them "
                "unverified, or call confirm_no_match."
            )
        }
    counts[name] = counts.get(name, 0) + 1
    return None


def _already_failed(name: str, args: dict, ctx) -> dict | None:
    failed = getattr(ctx, "failed_calls", None) or {}
    reason = failed.get(_call_key(name, args))
    if reason is None:
        return None
    return {
        "error": (
            f"This exact call already failed in this task ({reason}); it is not sent "
            "again. Try something different, or save or conclude from what you have."
        )
    }


def _remember_failure(name: str, args: dict, result: dict, ctx) -> None:
    error = result.get("error") if isinstance(result, dict) else None
    prefix = f"{name} failed: "
    if not isinstance(error, str) or not error.startswith(prefix):
        return  # a refusal or guidance, not a failure
    failed = _task_store(ctx, "failed_calls")
    if failed is not None:
        failed[_call_key(name, args)] = error[len(prefix) :].split(". ")[0][:160]


async def dispatch_batch(
    calls: list[tuple[str, dict]], ctx: ToolContext, task_type: str | None = None
) -> list[dict]:
    """Run one turn's tool calls, results in request order.

    Reads run concurrently; reads queued before a write flush first, so the model's ordering holds.
    """
    halted = None
    if any(name not in _HALT_EXEMPT for name, _ in calls):
        halted = await run_halted(ctx, task_type)

    # One registry round-trip per turn.
    names = [name for name, _ in calls]
    user_id = getattr(ctx, "user_id", None)
    states = await agents_registry.tool_states(
        ctx.session, user_id, agents_registry.WORKER_SCOPE, names
    )
    task_cfg = await agents_registry.task_state(ctx.session, user_id, task_type)
    allowed = list(task_cfg["tools"]) or None
    offered = getattr(ctx, "offered_tools", None)
    if offered is not None:
        allowed = [n for n in (allowed or offered) if n in offered]

    results: list[dict] = [{} for _ in calls]
    width = max(1, settings.agent_parallel_tool_calls)
    gate = asyncio.Semaphore(width)

    async def run_read(index: int, name: str, args: dict) -> None:
        async with gate:
            results[index] = await _invoke(name, args, ctx, halted, states, allowed)

    reads: list[asyncio.Task] = []

    async def flush() -> None:
        if reads:
            await asyncio.gather(*reads)
            reads.clear()

    remember: list[int] = []
    for index, (name, args) in enumerate(calls):
        read_only = _is_read_only(name, states)
        early = (
            _already_failed(name, args, ctx)
            if read_only and name not in _OPENALEX_TOOLS
            else None
        ) or _over_cap(name, ctx, task_type)
        if early is not None:
            results[index] = gates.with_gate(early)
            continue
        if read_only:
            if name not in _OPENALEX_TOOLS:
                remember.append(index)
            reads.append(asyncio.create_task(run_read(index, name, args)))
            continue
        await flush()
        results[index] = await _invoke(name, args, ctx, halted, states, allowed)
    await flush()
    for index in remember:
        name, args = calls[index]
        _remember_failure(name, args, results[index], ctx)
    return results
