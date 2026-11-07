"""Deterministic first pass for one professor.

Plain code does the lookups and scoring through the same tools (so
grounding, refusal codes and the trace still apply), and decides:

- **no_match**: unambiguous author scoring "unrelated"; concluded with
  confirm_no_match, no model call.
- **likely**: anything else unambiguous; one short tool-limited model call
  writes the cited rationale and saves (one repair turn on refusal).
- **agent**: hard cases (no single author, no works, OpenAlex down) go to
  the full agent loop.

OpenAlexBudgetExhausted / OpenAlexAuthError propagate so the task waits,
unless another verification source (sources.py) could verify them.
"""

from dataclasses import dataclass, field

from api.agent.orchestrator import RESULT_PREVIEW_CHARS
from api.agent.tool_preview import preview as tool_preview
from api.agent.tools import dispatch
from api.candidates import verification
from api.core.config import settings
from api.prospects import grounding, institutions, openalex, professor_index, sources

#: Works scored per author: enough to find the aligned paper of a prolific
#: PI, which the 15 most recent often miss.
SCORED_WORKS = 50
SCORED_YEARS = 5
BRIEF_WORKS = 5


@dataclass
class Decision:
    outcome: str  # "no_match" | "likely" | "agent"
    reason: str = ""
    candidate: dict = field(default_factory=dict)
    scored: dict = field(default_factory=dict)
    works: list[dict] = field(default_factory=list)
    #: Why an "agent" outcome fell back, a stable code for metrics.
    code: str = ""
    #: Awards still running for a likely match: a funding signal.
    grants: list[dict] = field(default_factory=list)
    #: Jev's fit rating, when one was asked for (verification.rate_fit).
    fit: dict | None = None


def _fits(fit: dict | None) -> bool:
    """A confident rating of related or better."""
    return bool(
        fit
        and fit["level"] >= verification.RELATED_LEVEL
        and fit["confidence"] >= settings.typesafe_auto_accept
    )


async def _emit(on_event, tool: str, tool_input: dict, result) -> None:
    if on_event is None:
        return
    await on_event(
        {
            "turn": 0,
            "tool": tool,
            "input": tool_input,
            "result": result,
            "result_preview": tool_preview(result, RESULT_PREVIEW_CHARS),
            "ok": not (isinstance(result, dict) and "error" in result),
        }
    )


async def _call(ctx, on_event, tool: str, tool_input: dict) -> dict:
    result = await dispatch(tool, tool_input, ctx)
    await _emit(on_event, tool, tool_input, result)
    return result


async def first_pass(ctx, school, name: str, on_event=None, indexed=None) -> Decision:
    """With an `indexed` professor index entry, nothing is fetched."""
    if indexed is not None:
        candidate = professor_index.use(ctx, indexed)
        works = list(indexed.works or [])
        await _emit(
            on_event,
            "professor_index",
            {"name": name},
            {
                "openalex_id": candidate["openalex_id"],
                "looked_up_at": indexed.looked_up_at.isoformat(),
                "count": len(works),
                "titles": [w.get("title") for w in works[:10]],
            },
        )
        return await _score(ctx, on_event, candidate, works, school, name)
    found = await _call(ctx, on_event, "find_openalex_author", {"name": name})
    if "error" in found:
        wait = getattr(ctx, "openalex_wait", None)
        if wait is not None:
            # Wait rather than hand the agent a professor it can't verify.
            raise wait
        return Decision("agent", "OpenAlex lookup failed", code="openalex_unavailable")
    school_id, school_names = await institutions.resolve_school(ctx.session, school)
    at_school = [
        c
        for c in found.get("candidates") or []
        if grounding.at_school(c, getattr(school, "name", None), school_id, school_names)
    ]
    if len(at_school) > 1:
        picked = await verification.pick_author(
            name, getattr(school, "name", "") or "", getattr(getattr(ctx, "program", None), "name", None),
            at_school, ctx.user_id,
        )
        await _emit(
            on_event,
            "jev_pick_author",
            {"name": name, "candidates": [c["openalex_id"] for c in at_school]},
            {"openalex_id": picked["openalex_id"]} if picked else {"error": "Jev couldn't tell them apart"},
        )
        if picked:
            at_school = [picked]
    if len(at_school) != 1:
        return Decision(
            "agent",
            "no author at the school" if not at_school else f"{len(at_school)} authors at the school",
            code="no_author_at_school" if not at_school else "multiple_authors",
        )
    candidate = at_school[0]
    author_id = candidate["openalex_id"]
    if grounding.is_source_id(author_id):
        # Another source's author: their works came with the lookup.
        works = grounding.works_for(ctx, author_id)
        await _emit(
            on_event,
            "get_author_works",
            {"openalex_id": author_id},
            {
                "count": len(works),
                "source": candidate.get("source"),
                "titles": [w.get("title") for w in works[:10]],
            },
        )
        return await _score(ctx, on_event, candidate, works, school, name, school_names)

    # Looked up before under another spelling or programme: reuse their works.
    known = await professor_index.lookup_author(ctx.session, ctx.user_id, author_id)
    if known is not None:
        indexed_works = list(known.works or [])
        professor_index.use(ctx, known)
        grounding.record_author_candidates(ctx, [candidate])
        await _emit(
            on_event,
            "professor_index",
            {"openalex_id": author_id},
            {
                "looked_up_at": known.looked_up_at.isoformat(),
                "count": len(indexed_works),
                "titles": [w.get("title") for w in indexed_works[:10]],
            },
        )
        return await _score(ctx, on_event, candidate, indexed_works, school, name)
    try:
        works = await openalex.get_recent_works(author_id, limit=SCORED_WORKS, years=SCORED_YEARS)
    except openalex.OpenAlexUnavailable as exc:
        if isinstance(exc, openalex.OpenAlexWait) and getattr(
            ctx, "park_on_openalex_budget", False
        ):
            raise
        # Recorded like the agent's lookups, so it can still save unverified.
        grounding.record_openalex_outcome(ctx, grounding.UNAVAILABLE)
        await _emit(on_event, "get_author_works", {"openalex_id": author_id}, {"error": str(exc)})
        return Decision("agent", "OpenAlex unavailable", code="openalex_unavailable")
    grounding.record_works(ctx, author_id, works)
    await _emit(
        on_event,
        "get_author_works",
        {"openalex_id": author_id, "limit": SCORED_WORKS, "years": SCORED_YEARS},
        {"count": len(works), "titles": [w.get("title") for w in works[:10]]},
    )
    if not works:
        # Only recent years were sampled; the agent establishes "no works".
        return Decision(
            "agent",
            f"no works in the last {SCORED_YEARS} years; get_author_works lists older ones",
            candidate,
            code="no_recent_works",
        )
    return await _score(ctx, on_event, candidate, works, school, name, school_names)


async def _score(
    ctx,
    on_event,
    candidate: dict,
    works: list[dict],
    school=None,
    name: str = "",
    school_names=(),
) -> Decision:
    """A likely match also carries any active grants."""
    author_id = candidate["openalex_id"]
    scored = await _call(ctx, on_event, "score_alignment", {"openalex_id": author_id})
    if "error" in scored:
        return Decision("agent", "scoring failed", candidate, code="scoring_failed")
    fit = None
    if scored.get("band") == "unrelated":
        # The similarity can miss the same work in other words: a confident
        # judgment that the papers fit keeps the professor.
        by_title = {(w.get("title") or "").strip(): w for w in works}
        closest = [by_title.get((t.get("title") or "").strip(), t) for t in scored.get("top_works") or []]
        fit = await verification.rate_fit(
            getattr(getattr(ctx, "run", None), "interest_statement", "") or "", closest, ctx.user_id
        )
        await _emit(on_event, "jev_rate_fit", {"openalex_id": author_id}, fit or {"error": "no rating"})
    if scored.get("band") == "unrelated" and not _fits(fit):
        via = sources.LABELS.get(candidate.get("source", ""))
        reason = (
            f"Scored {scored.get('score')} ({scored.get('method')}) on {len(works)} works "
            f"from the last {SCORED_YEARS} years"
            + (f" ({via}; {candidate.get('confidence')})" if via and candidate.get("confidence") else "")
            + ": unrelated to the student's interest."
        )
        confirmed = await _call(
            ctx, on_event, "confirm_no_match", {"reason": reason, "reason_code": "low_score"}
        )
        if "error" in confirmed:
            # Refused or failed: the agent can still conclude it properly.
            return Decision(
                "agent",
                f"no-match not recorded: {confirmed['error']}",
                candidate,
                scored,
                works,
                code="no_match_refused",
            )
        return Decision("no_match", reason, candidate, scored, works)
    decision = Decision("likely", "", candidate, scored, works, fit=fit)
    if candidate.get("source") in ("nih", "nsf"):
        decision.grants = list(candidate.get("active_grants") or [])
    else:
        decision.grants = await sources.active_grants(ctx, school, name, school_names)
    return decision


def save_brief(name: str, decision: Decision, interest: str) -> str:
    """The one-call brief: who, the score, and the best works to cite."""
    by_title = {(w.get("title") or "").strip(): w for w in decision.works}
    lines = []
    for top in (decision.scored.get("top_works") or [])[:BRIEF_WORKS]:
        work = by_title.get((top.get("title") or "").strip(), {})
        abstract = (work.get("abstract") or "").strip()
        if len(abstract) > 600:
            abstract = abstract[:600].rsplit(" ", 1)[0] + "…"
        lines.append(
            f"- \"{top.get('title')}\" ({top.get('year')}), match {top.get('score')}"
            + (f"\n  {abstract}" if abstract else "")
        )
    candidate = decision.candidate
    note = decision.scored.get("note")
    who = (
        f"{candidate.get('display_name')}, "
        f"{candidate.get('institution') or 'institution not listed'}"
    )
    via = sources.LABELS.get(candidate.get("source", "")) if candidate.get("source") != "orcid" else None
    author = (
        f"Author id (pass it as openalex_id): {candidate.get('openalex_id')} "
        f"(verified via {via}: {who}; {candidate.get('confidence')})\n"
        if via
        else f"OpenAlex author: {candidate.get('openalex_id')} ({who})\n"
    )
    grants = "".join(
        f"\n- \"{g.get('title')}\" ({g.get('source')}, runs until {g.get('ends')})"
        for g in decision.grants
    )
    return (
        f"Professor: {name}\n"
        + author
        + f"Alignment: similarity_score {decision.scored.get('score')} "
        f"(band {decision.scored.get('band')}, {decision.scored.get('method')} scoring)"
        + (f"\nNote: {note}" if note else "")
        + (
            f"\nThe similarity is low, but a judgment of the papers rated the fit "
            f"{decision.fit['label']} ({decision.fit['confidence']} confident): name the work that fits."
            if decision.fit
            else ""
        )
        + (
            "\nActive grants (a sign the lab can fund a student; mention one in the "
            "rationale if it is on the student's topic):" + grants
            if grants
            else ""
        )
        + f"\n\nStudent's research interest statement:\n{interest}\n\n"
        f"Best-matching works, already fetched and scored:\n" + "\n".join(lines)
    )


def enabled() -> bool:
    return settings.deterministic_research


__all__ = ["Decision", "enabled", "first_pass", "save_brief"]
