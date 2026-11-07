"""Prospect task handlers: discovery, supervisor fan-out, narrow worker."""

import time

from api.agent.orchestrator import add_task_time, run_agent_task, set_task_path
from api.agent.tools.context import ToolContext
from api.core.config import settings
from api.prospects.prompts import (
    DISCOVER_PROGRAMS_SYSTEM_PROMPT,
    INDEX_APPLICATION_MARKER,
    INDEX_APPLICATION_SYSTEM_PROMPT,
    RESEARCH_ONE_PROFESSOR_SYSTEM_PROMPT,
    RESEARCH_PROFESSOR_SYSTEM_PROMPT,
    ROSTER_EXTRACTION_SYSTEM_PROMPT,
    SAVE_ONE_PROFESSOR_SYSTEM_PROMPT,
)
from api.runs.budgets import run_limit


def _region_line(region: str | None) -> str:
    """The new-run composer sends "Anywhere" (or nothing) for no preference."""
    region = (region or "").strip()
    if not region or region.lower() == "anywhere":
        return "Anywhere (no regional preference: pick the strongest matches worldwide)"
    return region


def _field_line(field: str | None) -> str:
    """The composer leaves the field to the interest text when it can't read one."""
    return (field or "").strip() or "(not given: read it from the interest statement)"


async def run_discover_programs(
    session,
    task,
    run,
    on_event=None,
    resume_messages=None,
    on_checkpoint=None,
):
    from api.prospects import tiers

    program_cap = run_limit(run, "max_programs", settings.max_programs_per_run)
    # A shard of a split discovery: its tier or region, run in parallel.
    shard = getattr(task, "target_name", None) or None
    region = run.region
    chosen = tiers.load(run)
    share = tiers.shard_share(run, shard, program_cap)
    if shard and shard.startswith("tier:"):
        chosen = [shard.split(":", 1)[1]]
    elif shard and shard.startswith("region:"):
        region = shard.split(":", 1)[1]
    tier_block = tiers.brief(chosen, share)
    shard_line = (
        f"\nYou are one of several discovery tasks running in parallel; this one "
        f"covers only {shard.split(':', 1)[1]} and may save at most {share} programs."
        if shard
        else ""
    )
    user_message = (
        f"Target region: {_region_line(region)}\n"
        f"Field: {_field_line(run.field)}\n"
        f"Degree level: {run.degree_level}\n\n"
        f"Student's research interest statement (for context on sub-field focus):\n"
        f"{run.interest_statement}\n\n"
        + (f"{tier_block}\n\n" if tier_block else "")
        + f"Budget: save at most {min(settings.max_programs_per_task, share)} programs in this "
        f"task and {program_cap} "
        f"total for the run - prioritize the best-verified matches, then stop "
        f"and summarize. Call save_program as soon as each programme is "
        f"verified, several in one turn when you can: its faculty research "
        f"starts the moment it is saved.{shard_line}"
    )
    ctx = ToolContext(session=session, run=run)
    ctx.discovery_shard = shard
    result = await run_agent_task(
        DISCOVER_PROGRAMS_SYSTEM_PROMPT,
        user_message,
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        progress_tools={"save_program"},
        task_type="discover_programs",
    )
    return result
async def run_research_professor(
    session,
    task,
    run,
    on_event=None,
    resume_messages=None,
    on_checkpoint=None,
):
    """Queue faculty research, then index the programme's application."""
    from api.prospects import models as prospect_models

    program = await session.get(prospect_models.Program, task.target_id)
    school = await session.get(prospect_models.School, program.school_id)
    if program.user_id != run.user_id or school.user_id != run.user_id:
        raise RuntimeError(f"Program {task.target_id} is not owned by run {run.id}")

    if resume_messages and _starts_with(resume_messages, INDEX_APPLICATION_MARKER):
        return await _index_application(
            ctx_for_step(session, run, program), program, school,
            on_event=on_event, resume_messages=resume_messages, on_checkpoint=on_checkpoint,
        )
    result = await _research_faculty_roster(
        session, run, program, school, on_event=on_event,
        resume_messages=resume_messages, on_checkpoint=on_checkpoint,
    )
    indexed = await _index_application(
        ctx_for_step(session, run, program), program, school,
        on_event=on_event, on_checkpoint=on_checkpoint,
    )
    return _combined(result, indexed)


async def _research_faculty_roster(
    session, run, program, school, *, on_event=None, resume_messages=None, on_checkpoint=None,
):
    """Find the faculty list and queue one narrow task per name."""

    user_message = (
        f"Program: {program.name} at {school.name} ({school.country})\n"
        f"Department page: {program.department_url}\n"
        f"Degree level sought: {run.degree_level}\n\n"
        f"Student's research interest statement (for context on sub-field focus):\n"
        f"{run.interest_statement}\n\n"
        f"Your job in THIS task: find the current faculty list, then call "
        f"spawn_professor_research ONCE with every plausible name (at most "
        f"{run_limit(run, 'max_professors_per_program', settings.max_professors_per_program)} "
        f"will be queued for this program) and stop. "
        f"Do not research individual professors yourself."
    )
    ctx = ToolContext(session=session, run=run, program=program)
    from api.prospects import rosters

    key = rosters.roster_key(program.department_url)
    if resume_messages is None and settings.roster_min_names > 0:
        found = await _roster_first(session, ctx, program, key, on_event=on_event)
        if found is not None:
            return found
    result = await run_agent_task(
        RESEARCH_PROFESSOR_SYSTEM_PROMPT,
        user_message,
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        progress_tools={"spawn_professor_research", "confirm_no_match"},
        task_type="research_professor",
        # A fetch or two after the roster-first path missed, not the full budget.
        max_turns=settings.supervisor_max_turns,
    )
    spawned = [
        name
        for entry in result.get("tool_log") or []
        if entry.get("tool") == "spawn_professor_research"
        and "error" not in (entry.get("result") or {})
        for name in (entry.get("input") or {}).get("names") or []
    ]
    if spawned:
        await rosters.store(session, key, spawned, "agent")
        await session.commit()
        return result
    if settings.roster_min_names <= 0:
        return result
    # Last resort: OpenAlex authors at the school publishing on the topic.
    from api.prospects import institutions

    institution_id, _ = await institutions.resolve_school(session, school)
    limit = run_limit(run, "max_professors_per_program", settings.max_professors_per_program)
    seeded = await rosters.openalex_seed(institution_id, run.interest_statement, limit)
    if seeded:
        from api.prospects.pipeline import _call

        await _call(ctx, on_event, "spawn_professor_research", {"names": seeded})
        result = {
            **result,
            "final_text": (
                (result.get("final_text") or "")
                + f"\n\nNo faculty list was found, so {len(seeded)} authors OpenAlex places "
                "at the school, publishing on the student's topic there, were queued instead."
            ).strip(),
        }
    return result


async def _roster_first(session, ctx, program, key, *, on_event=None) -> dict | None:
    """The faculty list without the agent loop; None when too few names came
    back, for the agent to take over."""
    from api.prospects import rosters
    from api.prospects.pipeline import _call

    names = await rosters.stored(session, key)
    source = "stored"
    usage = {"input_tokens": 0, "output_tokens": 0}
    calls = 0
    if len(names) < settings.roster_min_names and program.department_url:
        names = []
        for url in rosters.listing_urls(program.department_url):
            text = await rosters.fetch_listing(url)
            if text is None:
                continue
            read = await run_agent_task(
                ROSTER_EXTRACTION_SYSTEM_PROMPT,
                f"Page: {url}\n\n{text}",
                ctx,
                on_event=on_event,
                task_type="research_professor",
                only_tools=set(),
                max_turns=1,
            )
            calls += 1
            for k in usage:
                usage[k] += (read.get("usage") or {}).get(k, 0)
            names = rosters.parse_names(read.get("final_text"))
            if len(names) >= settings.roster_min_names:
                source = url
                await rosters.store(session, key, names, "page")
                break
    if len(names) < settings.roster_min_names:
        return None
    queued = await _call(ctx, on_event, "spawn_professor_research", {"names": names})
    if "error" in queued:
        return None  # let the agent see the refusal and decide
    where = "a stored faculty list" if source == "stored" else source
    return {
        "final_text": f"Queued {queued.get('queued', 0)} of {len(names)} faculty names from {where}.",
        "tool_log": [],
        "turns": calls,
        "usage": usage,
        "nudges": 0,
    }


def _user_added_brief(openalex_id: str | None) -> str:
    text = (
        "\n\nThe student added this professor themselves: save them with "
        "whatever score score_alignment returns (don't call confirm_no_match "
        "for a low score). If OpenAlex can't confirm them, save them with "
        "unverified: true."
    )
    if openalex_id:
        text += (
            f" They gave the OpenAlex id {openalex_id}: use it with "
            "get_author_works instead of searching."
        )
    return text


async def run_research_one_professor(
    session,
    task,
    run,
    on_event=None,
    resume_messages=None,
    on_checkpoint=None,
):
    """Narrow worker: exactly one professor - OpenAlex disambiguation,
    recent works, alignment score, cited rationale, single save."""
    from api.prospects import models as prospect_models

    program = await session.get(prospect_models.Program, task.target_id)
    if program is None:
        raise RuntimeError(
            f"Program {task.target_id} not found for research task {task.id}"
        )
    if program.user_id != run.user_id:
        raise RuntimeError(f"Program {task.target_id} is not owned by run {run.id}")
    school = await session.get(prospect_models.School, program.school_id)
    if school.user_id != run.user_id:
        raise RuntimeError(f"School {program.school_id} is not owned by run {run.id}")
    name = task.target_name or "(unknown)"

    # A student-added professor is always researched and saved, outside the cap.
    from api.prospects.leads import run_candidate_room
    from api.prospects.tools import user_added_professor

    added = await user_added_professor(session, program.id, run.user_id, name)

    # Its save would be refused once the cap is full, so skip the model loop.
    cap, saved = await run_candidate_room(session, run, run.user_id)
    if saved >= cap and added is None:
        set_task_path("skipped", "run_cap")
        return {
            "final_text": (
                f"Skipped: the run already has {saved} candidates (cap {cap}); "
                f"{name} was not researched."
            ),
            "tool_log": [],
            "turns": 0,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "nudges": 0,
        }

    # A previously checkpointed admissions step may still belong to an older task.
    if resume_messages and _starts_with(resume_messages, INDEX_APPLICATION_MARKER):
        return await _index_application(
            ctx_for_step(session, run, program),
            program,
            school,
            on_event=on_event,
            resume_messages=resume_messages,
            on_checkpoint=on_checkpoint,
            task_type="research_one_professor",
        )
    user_message = (
        f"Professor: {name}\n"
        f"Program: {program.name} at {school.name} ({school.country})\n"
        f"Department page: {program.department_url}\n\n"
        f"Student's research interest statement:\n{run.interest_statement}\n\n"
        f"Research exactly this one professor: disambiguate on OpenAlex "
        f"(institution must match {school.name}), pull recent works, score "
        f"alignment, and save with a cited rationale - or explain in your "
        f"final summary why they are not a fit. Save at most one professor."
        + "\n\nDo not index the application; a separate step does that."
        + (_user_added_brief(added.openalex_id) if added is not None else "")
    )
    ctx = ToolContext(session=session, run=run, program=program)
    # While OpenAlex is out, wait (checkpoint kept) rather than spend tokens
    # on a save it can't verify.
    from api.prospects import openalex, pipeline, sources

    ctx.park_on_openalex_budget = True
    wait = openalex.wait_error()
    # Unless the code-first pass can verify them from another source.
    first_pass_covers = (
        added is None and resume_messages is None and pipeline.enabled()
        and sources.stands_in_for_openalex()
    )  # fmt: skip
    if wait is not None and not first_pass_covers:
        raise wait
    if added is not None:
        ctx.user_added = True
        if added.openalex_id:
            from api.prospects import grounding

            grounding.record_author_candidates(
                ctx, [{"openalex_id": added.openalex_id, "display_name": name}]
            )

    result = await _research_and_index(
        ctx,
        run,
        school,
        name,
        user_message,
        added,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
    )
    return result


def ctx_for_step(session, run, program) -> ToolContext:
    """A fresh context so each step has its own save counters and tool allowances."""
    return ToolContext(session=session, run=run, program=program)


def _has_model_turn(messages: list[dict]) -> bool:
    return any(m.get("role") == "assistant" for m in messages)


def _starts_with(messages: list[dict], marker: str) -> bool:
    first = next((m for m in messages if m.get("role") == "user"), None)
    content = first.get("content") if first else None
    return isinstance(content, str) and content.startswith(marker)


def _combined(first: dict, second: dict) -> dict:
    """One task result from two steps: both summaries, summed usage."""
    usage = {
        key: (first.get("usage") or {}).get(key, 0) + (second.get("usage") or {}).get(key, 0)
        for key in ("input_tokens", "output_tokens")
    }
    texts = [t for t in (first.get("final_text"), second.get("final_text")) if t]
    return {
        **first,
        "final_text": "\n\n".join(texts),
        "tool_log": (first.get("tool_log") or []) + (second.get("tool_log") or []),
        "turns": (first.get("turns") or 0) + (second.get("turns") or 0),
        "usage": usage,
        "nudges": (first.get("nudges") or 0) + (second.get("nudges") or 0),
    }


async def _index_application(
    ctx, program, school, *, on_event=None, resume_messages=None, on_checkpoint=None,
    task_type="research_professor",
) -> dict:
    """A short, tool-limited loop that saves the application, or nothing."""
    message = (
        f"{INDEX_APPLICATION_MARKER} {program.name} at {school.name} ({school.country}).\n"
        f"Department page: {program.department_url}\n"
        f"School website: {school.website_url}"
    )
    if on_checkpoint is not None and resume_messages is None:
        await on_checkpoint([{"role": "user", "content": message}])
    return await run_agent_task(
        INDEX_APPLICATION_SYSTEM_PROMPT,
        message,
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        task_type=task_type,
        finish_on={"save_application"},
        only_tools={"search_web", "fetch_page", "save_application"},
        max_turns=settings.index_application_max_turns,
    )


async def _research_and_index(
    ctx,
    run,
    school,
    name: str,
    user_message: str,
    added,
    *,
    on_event=None,
    resume_messages=None,
    on_checkpoint=None,
) -> dict:
    """The professor part, reading from and writing to the account's professor index."""
    from api.prospects import professor_index

    indexed = (
        await professor_index.lookup(ctx.session, ctx.user_id, school, name)
        if added is None and resume_messages is None
        else None
    )
    result = await _research_professor(
        ctx,
        run,
        school,
        name,
        user_message,
        added,
        indexed,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
    )
    await professor_index.remember(ctx, school, name)
    return result


async def _research_professor(
    ctx,
    run,
    school,
    name: str,
    user_message: str,
    added,
    indexed=None,
    *,
    on_event=None,
    resume_messages=None,
    on_checkpoint=None,
) -> dict:
    """The code-first pass, then the agent loop for the hard cases."""
    from api.prospects import pipeline, professor_index

    if resume_messages is not None and not _has_model_turn(resume_messages):
        # Nothing worth resuming before the first reply: start over, code first.
        resume_messages = None
    # Student-added professors are never concluded on a score alone, and
    # "user_added" goes first so lead release never counts them as a miss.
    skip_reason = (
        "user_added"
        if added is not None
        else "pipeline_off"
        if not pipeline.enabled()
        else "resume"
        if resume_messages is not None
        else None
    )
    set_task_path("agent", skip_reason)
    if skip_reason is None:
        started = time.perf_counter()
        decision = await pipeline.first_pass(ctx, school, name, on_event=on_event, indexed=indexed)
        add_task_time(tool=time.perf_counter() - started)
        set_task_path(decision.outcome, decision.code or None)
        if decision.outcome == "no_match":
            return {
                "final_text": f"Researched {name}, not a match: {decision.reason}",
                "tool_log": [],
                "turns": 0,
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "nudges": 0,
            }
        if decision.outcome == "likely":
            return await run_agent_task(
                SAVE_ONE_PROFESSOR_SYSTEM_PROMPT,
                pipeline.save_brief(name, decision, run.interest_statement),
                ctx,
                on_event=on_event,
                on_checkpoint=on_checkpoint,
                progress_tools={"save_professor_record", "confirm_no_match"},
                task_type="research_one_professor",
                finish_on={"save_professor_record", "confirm_no_match"},
                only_tools={"save_professor_record", "confirm_no_match"},
                # The save, plus one repair turn if a check refuses it.
                max_turns=2,
                small_model=True,
            )
        user_message += (
            f"\n\nA first pass looked them up on OpenAlex ({decision.reason}); "
            "what it found is already recorded, so you can save or conclude "
            "from it."
        )
    elif indexed is not None and skip_reason == "pipeline_off":
        author = professor_index.use(ctx, indexed)
        user_message += (
            f"\n\nYour account's professor index already has them: OpenAlex author "
            f"{author['openalex_id']} with {len(indexed.works or [])} recent works, looked "
            f"up {indexed.looked_up_at:%Y-%m-%d}. Both are recorded for this task: call "
            "score_alignment with that openalex_id instead of searching OpenAlex again."
        )

    result = await run_agent_task(
        RESEARCH_ONE_PROFESSOR_SYSTEM_PROMPT,
        user_message,
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        progress_tools={"save_professor_record", "confirm_no_match"},
        task_type="research_one_professor",
        # Skip the closing summary turn.
        finish_on={"save_professor_record", "confirm_no_match"},
    )
    return result
