"""Prospect DB-writing tools and their deterministic gates (budgets, caps,
citation check, dedup)."""

import asyncio
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from api.agent.tools.budgets import check_task_budget
from api.agent.tools.context import ToolContext
from api.candidates import models as candidate_models
from api.candidates import verification
from api.core.config import settings
from api.core.textnorm import normalize_text
from api.core.time import utcnow_naive
from api.index import sync as index_sync
from api.notifications import events as notification_events
from api.prospects import grounding, optouts, school_links, tiers, web
from api.prospects import models as prospect_models
from api.prospects.leads import release_deferred_leads
from api.runs import models as run_models
from api.runs.budgets import run_limit
from api.runs.lifecycle import note_work_enqueued
from api.runs.notify import notify_candidates


def _normalize(text: str) -> str:
    return normalize_text(text)


_MAX_IMAGE_URL = 2048


def image_url(value: object) -> str | None:
    """Only plain http(s): the UI hot-links it in an <img>."""
    if not isinstance(value, str):
        return None
    url = value.strip()
    if len(url) > _MAX_IMAGE_URL or not url.lower().startswith(("https://", "http://")):
        return None
    return url


def _merge_socials(stored: list | None, incoming: list | None) -> list:
    """Add links whose URL isn't stored yet; stored rows keep their labels."""
    seen: set[str] = set()
    merged = []
    for link in list(stored or []) + list(incoming or []):
        if not isinstance(link, dict):
            continue
        url = (link.get("url") or "").strip()
        label = (link.get("label") or "").strip()
        if not url or not label or url in seen:
            continue
        seen.add(url)
        merged.append({"label": label, "url": url})
    return merged


def verify_professor_save(tool_input: dict) -> str | None:
    """The rationale must cite a fetched paper; an error message, or None."""
    rationale = _normalize(tool_input.get("rationale") or "")
    papers = tool_input.get("papers") or []
    if not rationale:
        return "Rationale is empty - write 1-3 sentences citing the specific papers that align."
    for p in papers:
        title = _normalize(p.get("title") or "")
        if not title:
            continue
        if title in rationale:
            return None
        words = title.split()
        for i in range(len(words) - 4):
            window = " ".join(words[i : i + 5])
            if len(window) >= 20 and window in rationale:
                return None
    titles = [p.get("title") or "(untitled)" for p in papers]
    return (
        "Rationale does not cite any of the fetched papers - quote or closely "
        f"name one of these titles instead of describing the work generally: {titles}"
    )


async def existing_professor(ctx: ToolContext, tool_input: dict):
    """The saved professor for this program + OpenAlex id, or None."""
    openalex_id = tool_input.get("openalex_id")
    if not openalex_id or ctx.program is None:
        return None
    if grounding.is_source_id(openalex_id):
        return await _existing_from_source(ctx, tool_input)
    result = await ctx.session.execute(
        select(prospect_models.Professor).where(
            prospect_models.Professor.program_id == ctx.program.id,
            prospect_models.Professor.user_id == ctx.user_id,
            prospect_models.Professor.openalex_id == openalex_id,
        )
    )
    return result.scalar_one_or_none()


async def _existing_from_source(ctx: ToolContext, tool_input: dict):
    """Without an OpenAlex id, match the same name with that source's profile link."""
    candidate = (getattr(ctx, "author_candidates", None) or {}).get(
        grounding.author_key(str(tool_input.get("openalex_id")))
    )
    urls = {link["url"] for link in (candidate or {}).get("links") or []}
    name = (tool_input.get("name") or "").strip().lower()
    if not urls or not name:
        return None
    rows = (
        await ctx.session.execute(
            select(prospect_models.Professor).where(
                prospect_models.Professor.program_id == ctx.program.id,
                prospect_models.Professor.user_id == ctx.user_id,
                prospect_models.Professor.openalex_id.is_(None),
                func.lower(prospect_models.Professor.name) == name,
            )
        )
    ).scalars().all()
    return next(
        (p for p in rows if urls & {s.get("url") for s in p.socials or [] if isinstance(s, dict)}),
        None,
    )


async def complete_dedup(ctx: ToolContext, tool_input: dict, professor) -> dict:
    """The saved professor and its candidate, created if the earlier attempt died first."""
    # Scoped to this run: a shared programme's professor is scored per run.
    result = await ctx.session.execute(
        select(candidate_models.CandidateScore).where(
            candidate_models.CandidateScore.professor_id == professor.id,
            candidate_models.CandidateScore.user_id == ctx.user_id,
            candidate_models.CandidateScore.run_id == ctx.run.id,
        )
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        # The score must still be the tool's, never the model's word.
        school = await ctx.session.get(prospect_models.School, ctx.program.school_id)
        from api.prospects import institutions

        school_id, school_names = (
            institutions.stored(school) if school is not None else (None, [])
        )
        error, tool_input = grounding.ground_professor_save(
            tool_input,
            ctx,
            school.name if school is not None else None,
            school_id,
            school_names,
        )
        if error is not None:
            return {"error": error}
        candidate = candidate_models.CandidateScore(
            run_id=ctx.run.id,
            user_id=ctx.user_id,
            professor_id=professor.id,
            similarity_score=tool_input["similarity_score"],
            rationale=tool_input["rationale"],
            status=candidate_models.CandidateStatus.scored,
        )
        ctx.session.add(candidate)
        await ctx.session.flush()
        await notification_events.first_candidate(ctx.session, ctx.run, candidate.id)

    # Fill-empty-only: a retry must not clobber what the first save recorded.
    if not professor.lab_name and tool_input.get("lab_name"):
        professor.lab_name = tool_input["lab_name"]
    if not professor.bio and tool_input.get("bio"):
        professor.bio = tool_input["bio"]
        professor.bio_source = tool_input.get("bio_source")
    if not professor.photo_url and image_url(tool_input.get("photo_url")):
        professor.photo_url = image_url(tool_input.get("photo_url"))
    merged_socials = _merge_socials(professor.socials, tool_input.get("socials"))
    if len(merged_socials) != len(professor.socials or []):
        professor.socials = merged_socials

    await index_sync.sync_candidate_id(ctx.session, candidate.id)
    ctx.last_candidate_id = candidate.id
    await notify_candidates(ctx.session, ctx.run.id)
    await ctx.session.commit()
    return {
        "professor_id": professor.id,
        "candidate_id": candidate.id,
        "deduped": True,
        "note": "Professor was already saved for this program; returning the existing record.",
    }


async def fetch_existing_professor_result(ctx: ToolContext, tool_input: dict) -> dict:
    """Polls briefly: a concurrent winner may have flushed but not committed. The
    last resort is a retry error, never a claim the save failed."""
    if ctx.program is None:
        return {"error": "Duplicate professor save failed: no program in context."}
    professor = await existing_professor(ctx, tool_input)
    for delay in (0.2, 0.5, 1.0):
        if professor is not None:
            break
        await asyncio.sleep(delay)
        professor = await existing_professor(ctx, tool_input)
    if professor is None:
        return {
            "error": (
                "Another worker appears to be saving this same professor "
                "concurrently; retry this save once."
            )
        }
    return await complete_dedup(ctx, tool_input, professor)


async def _tier_for_new_school(ctx: ToolContext, tool_input: dict):
    """(tier, refusal): the tier must be one the run chose, within its share of the cap."""
    chosen = tiers.load(ctx.run)
    if not chosen:
        return None, None
    tier = str(tool_input.get("school_tier") or "").strip().lower()
    if tier not in chosen:
        return None, (
            f"This run targets {', '.join(chosen)} schools. Pass school_tier as "
            f"one of those for this school, or skip it if it's in another tier."
        )
    cap = run_limit(ctx.run, "max_programs", settings.max_programs_per_run)
    share = tiers.quotas(chosen, cap)[tier]
    in_tier = await school_links.count_links(ctx.session, ctx.run.id, origin="agent", tier=tier)
    if in_tier >= share:
        others = [t for t in chosen if t != tier]
        return None, (
            f"The {tier} tier already has its share ({in_tier} of {share} schools). "
            f"Find schools in the other target tiers ({', '.join(others)}) instead."
        )
    return tier, None


async def discovery_complete(session, run, shard: str | None) -> str | None:
    """Why a discovery task is done (school budget or tier share full), else None."""
    cap = run_limit(run, "max_programs", settings.max_programs_per_run)
    saved = await school_links.count_links(session, run.id, origin="agent")
    if saved >= cap:
        return f"The run's school budget is reached ({saved} of {cap} schools saved); discovery is complete."
    chosen = tiers.load(run)
    tier = shard[5:] if shard and shard.startswith("tier:") else None
    if tier and tier in chosen:
        share = tiers.quotas(chosen, cap)[tier]
        in_tier = await school_links.count_links(session, run.id, origin="agent", tier=tier)
        if in_tier >= share:
            return f"The {tier} tier's share of the school budget is saved ({in_tier} of {share}); discovery is complete."
    return None


async def handle_save_program(tool_input: dict, ctx: ToolContext) -> dict:
    """Save a school + programme and queue its faculty research.

    Existing schools and programmes are reused and linked. Idempotent per
    run on (school, programme): a re-issued save returns the existing ids
    and queues nothing. An advisory lock on the account serializes saves.
    """
    await school_links.lock_account(ctx.session, ctx.user_id)
    picture = image_url(tool_input.get("school_image_url"))
    school = await school_links.find_school(
        ctx.session,
        ctx.user_id,
        name=tool_input["school_name"],
        website_url=tool_input.get("school_website"),
    )
    existing = (
        await school_links.find_program(
            ctx.session,
            school.id,
            name=tool_input["program_name"],
            department_url=tool_input.get("department_url"),
        )
        if school is not None
        else None
    )
    linked = (
        school is not None
        and await school_links.run_link(ctx.session, ctx.run.id, school.id) is not None
    )
    if linked and existing is not None and await school_links.program_in_run(
        ctx.session, ctx.run.id, existing.id
    ):
        school_links.fill_school(school, image_url=picture)
        await ctx.session.commit()  # release the lock
        return {"school_id": school.id, "program_id": existing.id, "deduped": True}

    refusal = check_task_budget(ctx, "programs")
    if refusal is not None:
        await ctx.session.commit()
        return {
            **refusal,
            "task_complete": f"Saved the {ctx.programs_saved} programmes this task may save; discovery is complete.",
        }
    # Saves a person approved in chat have their own cap.
    origin = "agent" if getattr(ctx, "metered", True) else "user"
    saved = await school_links.count_links(ctx.session, ctx.run.id, origin=origin)
    # A new programme at a school this run already has spends no school cap.
    limit_error = None
    complete = None
    if not linked and origin == "agent":
        program_limit = run_limit(
            ctx.run, "max_programs", settings.max_programs_per_run
        )
        if saved >= program_limit:
            limit_error = (
                f"Run program budget reached ({program_limit} schools saved). "
                "Do not save more programs; write your final summary instead."
            )
            complete = (
                f"The run's school budget is reached ({program_limit} of "
                f"{program_limit} schools saved); discovery is complete."
            )
    elif not linked and saved >= settings.max_user_programs_per_run:
        limit_error = (
            f"You've added {saved} schools to this run, the most allowed "
            f"({settings.max_user_programs_per_run}). Start a new run for more."
        )
    tier = None
    if limit_error is None and not linked and origin == "agent":
        tier, limit_error = await _tier_for_new_school(ctx, tool_input)
        shard = getattr(ctx, "discovery_shard", None)
        if limit_error and shard and shard == f"tier:{tool_input.get('school_tier', '')}".lower():
            complete = f"The {shard[5:]} tier's share of the school budget is saved; discovery is complete."
    if limit_error is not None:
        await ctx.session.commit()  # release the lock
        # A full budget ends the task as done, not as a refusal to work around.
        return {"error": limit_error, **({"task_complete": complete} if complete else {})}
    if school is None:
        school = prospect_models.School(
            tier=tier,
            origin=origin,
            user_id=ctx.user_id,
            name=tool_input["school_name"],
            country=tool_input.get("school_country"),
            website_url=tool_input.get("school_website"),
            image_url=picture,
        )
        ctx.session.add(school)
        await ctx.session.flush()
    else:
        # A person-added school (no tier) takes the first tier discovery gives it.
        school_links.fill_school(
            school,
            country=tool_input.get("school_country"),
            website_url=tool_input.get("school_website"),
            image_url=picture,
        )
        if tier and not school.tier:
            school.tier = tier
    if not linked:
        await school_links.link_school(
            ctx.session, ctx.run.id, school, origin=origin, tier=tier
        )

    program = existing
    if program is None:
        program = prospect_models.Program(
            school_id=school.id,
            user_id=ctx.user_id,
            name=tool_input["program_name"],
            department_url=tool_input.get("department_url"),
        )
        ctx.session.add(program)
        await ctx.session.flush()
    elif not program.department_url and tool_input.get("department_url"):
        program.department_url = tool_input.get("department_url")

    # A programme another run found is researched again: candidates are per run.
    ctx.session.add(
        run_models.ResearchTask(
            run_id=ctx.run.id,
            user_id=ctx.user_id,
            task_type="research_professor",
            target_id=program.id,
            target_name=school.name,
        )
    )
    await note_work_enqueued(ctx.session, ctx.run.id)
    await ctx.session.commit()
    ctx.programs_saved += 1
    return {
        "school_id": school.id,
        "program_id": program.id,
        **({"reused": True} if existing is not None else {}),
    }


async def handle_save_professor_record(tool_input: dict, ctx: ToolContext) -> dict:
    if ctx.program is None:
        return {
            "error": "No program in context; this task type can't save a professor."
        }

    # Dedup first, so retries never see a spurious budget refusal.
    duplicate = await existing_professor(ctx, tool_input)
    if duplicate is not None:
        return await complete_dedup(ctx, tool_input, duplicate)

    school_row = await ctx.session.get(prospect_models.School, ctx.program.school_id)
    if await optouts.is_opted_out(
        ctx.session,
        openalex_id=tool_input.get("openalex_id"),
        name=tool_input.get("name"),
        school=school_row.name if school_row is not None else None,
    ):
        return {
            "error": (
                "This person asked not to be included in Graduator. Don't save "
                "them; call confirm_no_match and move on."
            )
        }

    refusal = check_task_budget(ctx, "professors")
    if refusal is not None:
        return refusal

    # Live COUNT; parallel workers can overshoot by a row or two.
    run_count = (
        await ctx.session.execute(
            select(func.count())
            .select_from(candidate_models.CandidateScore)
            .where(
                candidate_models.CandidateScore.run_id == ctx.run.id,
                candidate_models.CandidateScore.user_id == ctx.user_id,
            )
        )
    ).scalar() or 0
    professor_limit = run_limit(
        ctx.run, "max_professors", settings.max_candidates_per_run
    )
    if run_count >= professor_limit and not getattr(ctx, "user_added", False):
        return {
            "error": (
                f"Run candidate budget reached ({professor_limit} "
                f"candidates saved, {run_count} on record). Do not save more "
                "professors for this run; write your final summary instead."
            )
        }

    if tool_input.get("unverified"):
        # Saved flagged, with no papers or score, rather than lost.
        unverified_error = grounding.unverified_save_error(ctx, tool_input)
        if unverified_error is not None:
            return {"error": unverified_error}
        return await _store_professor(
            ctx,
            {**tool_input, "papers": [], "similarity_score": None},
            rationale=f"Unverified: {tool_input['rationale'].strip()}",
        )

    # Store what the tools returned, not what the model says they returned.
    school = await ctx.session.get(prospect_models.School, ctx.program.school_id)
    from api.prospects import institutions

    school_id, school_names = (
        institutions.stored(school) if school is not None else (None, [])
    )
    grounding_error, tool_input = grounding.ground_professor_save(
        tool_input,
        ctx,
        school.name if school is not None else None,
        school_id,
        school_names,
    )
    if grounding_error is not None:
        return {"error": grounding_error}

    verification_error = verify_professor_save(tool_input)
    verification_result = None
    if verification_error is not None:
        # Paraphrased-but-true rationales fail the substring gate; only an
        # auto-accepted Jev judgment overrides the refusal.
        judgment = await verification.maybe_verify_rationale(tool_input, ctx.user_id)
        if judgment is None or not judgment["auto"]:
            if judgment is not None:
                verification_error += (
                    f" (semantic check: {judgment['verdict']} "
                    f"at confidence {judgment['confidence']:.2f})"
                )
            return {"error": verification_error}
        verification_result = {
            "method": "typesafe",
            "verdict": judgment["verdict"],
            "confidence": judgment["confidence"],
            "model": judgment["model"],
        }

    result = await _store_professor(ctx, tool_input, rationale=tool_input["rationale"])
    if verification_result is not None and "candidate_id" in result:
        result["verification"] = verification_result  # type: ignore
    return result


async def user_added_professor(session, program_id: str, user_id: str, name: str):
    """Agent saves create a row with its candidate, so an unscored row is student-added."""
    rows = (
        await session.execute(
            select(prospect_models.Professor).where(
                prospect_models.Professor.program_id == program_id,
                prospect_models.Professor.user_id == user_id,
                func.lower(prospect_models.Professor.name) == name.strip().lower(),
            )
        )
    ).scalars().all()
    for row in rows:
        scored = (
            await session.execute(
                select(func.count())
                .select_from(candidate_models.CandidateScore)
                .where(candidate_models.CandidateScore.professor_id == row.id)
            )
        ).scalar()
        if not scored:
            return row
    return None


async def _store_professor(ctx: ToolContext, tool_input: dict, *, rationale: str) -> dict:
    """Write the professor, their papers and the candidate row."""
    # The supervisor's faculty listing may have shown a portrait.
    photo = image_url(tool_input.get("photo_url"))
    if photo is None:
        school = await ctx.session.get(prospect_models.School, ctx.program.school_id)
        photo = web.portrait_for(
            tool_input["name"],
            [ctx.program.department_url, school.website_url if school is not None else None],
        )
    professor = (
        await user_added_professor(ctx.session, ctx.program.id, ctx.user_id, tool_input["name"])
        if getattr(ctx, "user_added", False)
        else None
    )
    if professor is not None:
        for key in ("profile_url", "openalex_id", "lab_name", "bio", "bio_source"):
            if tool_input.get(key) and not getattr(professor, key):
                setattr(professor, key, tool_input[key])
        if not professor.photo_url:
            professor.photo_url = photo
        professor.socials = _merge_socials(professor.socials or [], tool_input.get("socials"))
    else:
        professor = prospect_models.Professor(
            program_id=ctx.program.id,
            user_id=ctx.user_id,
            name=tool_input["name"],
            profile_url=tool_input.get("profile_url"),
            openalex_id=tool_input.get("openalex_id"),
            lab_name=tool_input.get("lab_name"),
            bio=tool_input.get("bio"),
            bio_source=tool_input.get("bio_source"),
            photo_url=photo,
            socials=_merge_socials([], tool_input.get("socials")),
        )
        ctx.session.add(professor)
    try:
        await ctx.session.flush()
    except IntegrityError:
        # Same OpenAlex author already saved for this program: hand that back.
        await ctx.session.rollback()
        return await fetch_existing_professor_result(ctx, tool_input)

    for p in tool_input.get("papers", []):
        ctx.session.add(
            prospect_models.Paper(
                professor_id=professor.id,
                user_id=ctx.user_id,
                title=p["title"],
                abstract=p.get("abstract"),
                year=p.get("year"),
                url=p.get("url"),
                citations=p.get("citations"),
                publication_type=p.get("publication_type"),
                coauthors=p.get("coauthors"),
            )
        )

    candidate = candidate_models.CandidateScore(
        run_id=ctx.run.id,
        user_id=ctx.user_id,
        professor_id=professor.id,
        similarity_score=tool_input["similarity_score"],
        rationale=rationale,
        status=candidate_models.CandidateStatus.scored,
    )
    ctx.session.add(candidate)
    await ctx.session.flush()
    await notification_events.first_candidate(ctx.session, ctx.run, candidate.id)
    await index_sync.sync_candidate_id(ctx.session, candidate.id)

    ctx.last_candidate_id = candidate.id
    ctx.professors_saved += 1
    await notify_candidates(ctx.session, ctx.run.id)
    await ctx.session.commit()
    return {"professor_id": professor.id, "candidate_id": candidate.id}


async def handle_spawn_professor_research(tool_input: dict, ctx: ToolContext) -> dict:
    if ctx.program is None:
        return {"error": "No program in context; nothing to spawn research for."}
    from api.runs.agents import is_cancelled

    if is_cancelled(ctx.run, "research_one_professor"):
        return {
            "error": (
                "The Professor Agents were cancelled for this run, so no names are "
                "queued. Write your final summary."
            )
        }
    queued_rows = (
        await ctx.session.execute(
            select(run_models.ResearchTask.target_name).where(
                run_models.ResearchTask.run_id == ctx.run.id,
                run_models.ResearchTask.user_id == ctx.user_id,
                run_models.ResearchTask.task_type == "research_one_professor",
                run_models.ResearchTask.target_id == ctx.program.id,
            )
        )
    ).all()
    seen = {(row[0] or "").strip().lower() for row in queued_rows}
    school_row = await ctx.session.get(prospect_models.School, ctx.program.school_id)
    school_name = school_row.name if school_row is not None else None
    names = []
    for raw in tool_input.get("names") or []:
        name = (raw or "").strip()
        key = name.lower()
        if name and await optouts.is_opted_out(
            ctx.session, name=name, school=school_name
        ):
            continue
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    # Names are kept as deferred leads; leads.py releases them by fair share.
    room = max(settings.max_spawn_per_call - len(queued_rows), 0)
    if room == 0 and names:
        return {
            "error": (
                f"This program already has {len(queued_rows)} names queued. "
                "Do not queue more; write your final summary instead."
            )
        }
    from api.prospects import ranking

    names, ranked = await ranking.rank_by_topic(
        ctx.session, school_row, ctx.run.interest_statement, names
    )
    names = names[:room]
    base = utcnow_naive()
    leads = []
    for i, name in enumerate(names):
        lead = run_models.ResearchTask(
            run_id=ctx.run.id,
            user_id=ctx.user_id,
            task_type="research_one_professor",
            target_id=ctx.program.id,
            target_name=name,
            status=run_models.TaskStatus.deferred,
            # Distinct timestamps keep the ranking; leads release oldest first.
            created_at=base + timedelta(microseconds=i),
        )
        ctx.session.add(lead)
        leads.append(lead)
    if names:
        await ctx.session.flush()
        await release_deferred_leads(ctx.session, ctx.run.id)
        await note_work_enqueued(ctx.session, ctx.run.id)
    await ctx.session.commit()
    started = [
        lead.target_name
        for lead in leads
        if run_models.status_str(lead.status) == run_models.TaskStatus.pending.value
    ]
    return {
        "queued": len(names),
        "ranked_by_topic": ranked,
        "researching_now": len(started),
        "waiting": len(names) - len(started),
        "names": names,
        "note": (
            "Each name now has its own research task; names past this "
            "program's share wait and start as slots free up. Your part is "
            "done - write your final summary."
            if names
            else "No valid names given; nothing queued."
        ),
    }
