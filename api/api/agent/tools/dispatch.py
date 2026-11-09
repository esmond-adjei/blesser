"""Route each agent tool call to its handler.

A new tool needs a HANDLERS row and a definition in definitions.py (parity is tested).
"""

import asyncio
import json

from api import web
from api.agent.tools.context import ToolContext
from api.core.config import settings
from api.opportunities import tools as opportunity_tools

__all__ = ["HANDLERS", "READ_ONLY_TOOLS", "ToolContext", "dispatch_batch", "run_halted"]


async def _search_web(tool_input: dict, ctx: ToolContext) -> dict:
    reused = web.reusable_search(tool_input["query"])
    if reused is not None:
        return {"results": web.brief_results(reused)}
    results = await web.search_web(tool_input["query"])
    return {"results": web.brief_results(results)}


async def _fetch_page(tool_input: dict, ctx: ToolContext) -> dict:
    from api.opportunities.page_content import Page, expired, page_note

    key = opportunity_tools.url_key(tool_input["url"])
    if key in ctx.known_pages and not ctx.reverify_id:
        note = ctx.known_pages[key]
        return {
            "text": "Skip known URL. " + note,
            "page_note": note,
            "cached_summary": True,
        }
    offset = max(0, tool_input.get("offset") or 0)
    async with ctx.fetch_locks.setdefault(key, asyncio.Lock()):
        if (key, offset) in ctx.fetch_windows:
            if key not in ctx.fetched_pages:
                from api.opportunities.page_cache import get_page

                page = await get_page(tool_input["url"])
                if not page.error:
                    opportunity_tools.record_fetch(ctx, key, page.text)
            return {
                "text": "Already read. " + ctx.page_notes.get(key, key),
                "cached_summary": True,
            }
        text = await web.fetch_page(
            tool_input["url"],
            max_chars=settings.fetch_max_chars,
            offset=offset,
            persistent=True,
        )
        ctx.fetch_windows.add((key, offset))
        opportunity_tools.record_fetch(ctx, tool_input["url"], text)
        closed = expired(text, {}, opportunity_tools.opp_service.today())
        verdict = (
            "fetch failed"
            if text.startswith("[Could not fetch")
            else "closed"
            if closed
            else "read"
        )
        ctx.page_notes[key] = page_note(
            Page(url=key, text=text, title=text.splitlines()[0][:120] if text else ""),
            verdict,
        )
        if closed:
            from api.core.db import SessionLocal
            from api.opportunities.crawler import record_candidate

            async with SessionLocal() as session:
                await record_candidate(
                    session,
                    key,
                    category_hints=[ctx.category],
                    status="closed",
                    reason="deadline_passed",
                )
                await session.commit()
        result = {"text": text, "page_note": ctx.page_notes[key]}
        if verdict == "fetch failed":
            result["error"] = text
        return result


HANDLERS = {
    "search_web": _search_web,
    "fetch_page": _fetch_page,
    "save_opportunity": opportunity_tools.handle_save_opportunity,
    "reject_candidate": opportunity_tools.handle_reject_candidate,
}

#: Safe to run concurrently: they never touch the (not concurrency-safe) DB session.
READ_ONLY_TOOLS = frozenset({"search_web", "fetch_page"})


async def run_halted(ctx: ToolContext) -> str | None:
    """Why this task must stop: its run was cancelled, or this attempt was superseded."""
    from api.scans.queue import current_lease_halt

    await ctx.session.refresh(ctx.run, attribute_names=["status"])
    if ctx.run.status == "cancelled":
        return "cancelled"
    task_halt = await current_lease_halt(ctx.session)
    return f"task {task_halt}" if task_halt else None


async def _invoke(name: str, args: dict, ctx: ToolContext, halted: str | None) -> dict:
    """Never raises: inside a gather an exception would also discard its siblings' work."""
    if halted is not None:
        return {
            "error": f"This task was halted ({halted}); write your final summary instead."
        }
    offered = getattr(ctx, "offered_tools", None)
    if offered is not None and name not in offered:
        return {"error": f"Tool {name} is not available in this task."}
    handler = HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await handler(args, ctx)
    except Exception as exc:  # noqa: BLE001 - surface to the agent, don't kill the task
        return {"error": f"{name} failed: {exc}"}


def _call_key(name: str, args: dict) -> str:
    return name + json.dumps(args, sort_keys=True, default=str)


async def dispatch_batch(calls: list[tuple[str, dict]], ctx: ToolContext) -> list[dict]:
    """Run one turn's tool calls, results in request order.

    Reads run concurrently; reads queued before a write finish first, so the model's
    ordering holds. A read that already failed in this task is not sent again.
    """
    halted = await run_halted(ctx) if getattr(ctx, "run", None) is not None else None
    results: list[dict] = [{} for _ in calls]
    gate = asyncio.Semaphore(max(1, settings.agent_parallel_tool_calls))
    failed = getattr(ctx, "failed_calls", None)
    if failed is None:
        failed = {}
    reads: list[asyncio.Task] = []

    async def run_read(index: int, name: str, args: dict) -> None:
        async with gate:
            results[index] = await _invoke(name, args, ctx, halted)
        error = results[index].get("error")
        if isinstance(error, str) and error.startswith(f"{name} failed: "):
            failed[_call_key(name, args)] = error.split(": ", 1)[1][:160]

    async def flush() -> None:
        if reads:
            await asyncio.gather(*reads)
            reads.clear()

    for index, (name, args) in enumerate(calls):
        if name in READ_ONLY_TOOLS:
            reason = failed.get(_call_key(name, args))
            if reason is not None:
                results[index] = {
                    "error": (
                        f"This exact call already failed in this task ({reason}); it is not "
                        "sent again. Try something different."
                    )
                }
                continue
            reads.append(asyncio.create_task(run_read(index, name, args)))
            continue
        await flush()
        results[index] = await _invoke(name, args, ctx, halted)
    await flush()
    return results
