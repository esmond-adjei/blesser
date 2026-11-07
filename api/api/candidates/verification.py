"""Jev-backed second-stage rationale check (TypeSafe System One).

Three judgments, each behind its flag and the daily tool allowance, each
returning None when it can't answer (off, unkeyed, over allowance, outage)
so the caller keeps its own behaviour:

- the rationale check: the exact-substring gate false-refuses paraphrase;
  this judges it. Fail closed: an outage never auto-passes a rationale;
- pick_author: which of several same-name authors at a school is the professor;
- rate_fit: how well a professor's papers fit the student's interests.
"""

from typesafe_sdk import AsyncTypeSafeClient, Choice, Score

from api.core.config import settings

RELATION_TO_VERDICT = {
    "supports": "verified",
    "contradicts": "contradicted",
    "says_nothing": "unsupported",
}

CITATION_QUESTION = Choice(
    instructions=(
        "How do the fetched papers relate to the rationale? Judge the "
        "rationale's claim about research alignment against the paper "
        "titles and abstracts as the source of truth."
    ),
    criteria={
        "supports": (
            "The papers state the rationale's alignment claim or directly "
            "imply that it is true. A claim that paraphrases a paper's "
            "topic in different words still counts as support; only the "
            "meaning has to match, not the wording."
        ),
        "contradicts": (
            "The papers state the opposite of the claim or imply it is false"
        ),
        "says_nothing": (
            "The papers do not address what the rationale asserts, either way"
        ),
    },
)


def _evidence(
    papers: list[dict], max_papers: int = 8, max_chars: int = 1500
) -> list[dict]:
    """Trim papers to title + bounded abstract so state stays small."""
    evidence = []
    for p in (papers or [])[:max_papers]:
        abstract = p.get("abstract") or ""
        evidence.append(
            {"title": p.get("title") or "(untitled)", "abstract": abstract[:max_chars]}
        )
    return evidence


async def check_rationale_citation(
    rationale: str, papers: list[dict], *, api_key: str, model: str, auto_accept: float
) -> dict:
    """Ask Jev whether the papers support the rationale; returns {"verdict",
    "confidence", "auto", "model"}."""
    async with AsyncTypeSafeClient(api_key=api_key) as client:
        response = await client.system_one(
            state={"rationale": rationale, "papers": _evidence(papers)},
            questions={"citation": CITATION_QUESTION},
            model=model,
        )
    answer = response.answers["citation"]
    verdict = RELATION_TO_VERDICT.get(getattr(answer, "choice", ""), "unsupported")
    confidence = getattr(answer, "confidence", None) or 0.0
    return {
        "verdict": verdict,
        "confidence": confidence,
        "auto": verdict == "verified" and confidence >= auto_accept,
        "model": getattr(response, "model", model),
    }


async def maybe_verify_rationale(
    tool_input: dict, user_id: str | None = None
) -> dict | None:
    """Judgment dict, or None when off, unkeyed, over the daily tool allowance, or
    failing (caller keeps the deterministic verdict)."""
    if not settings.typesafe_rationale_check or not settings.typesafe_api_key:
        return None
    from api.billing import service as billing

    if await billing.tool_call_refusal(
        user_id, "verification", "typesafe", settings.typesafe_model
    ):
        return None
    try:
        return await check_rationale_citation(
            tool_input.get("rationale") or "",
            tool_input.get("papers") or [],
            api_key=settings.typesafe_api_key,
            model=settings.typesafe_model,
            auto_accept=settings.typesafe_auto_accept,
        )
    except Exception:  # noqa: BLE001 - fail closed to the deterministic refusal
        return None


async def _allowed(flag: bool, user_id: str | None) -> bool:
    if not flag or not settings.typesafe_api_key:
        return False
    from api.billing import service as billing

    return not await billing.tool_call_refusal(user_id, "verification", "typesafe", settings.typesafe_model)


async def _ask(state: dict, question) -> object:
    async with AsyncTypeSafeClient(api_key=settings.typesafe_api_key) as client:
        response = await client.system_one(state=state, questions={"q": question}, model=settings.typesafe_model)
    return response.answers["q"]


NOT_THEM = "none"


async def pick_author(
    name: str, school: str, programme: str | None, candidates: list[dict], user_id: str | None = None
) -> dict | None:
    """The candidate Jev is confident is the professor, or None (not
    confident, none of them, or no answer)."""
    if len(candidates) < 2 or not await _allowed(settings.typesafe_author_pick, user_id):
        return None
    options = {f"author_{i}": c for i, c in enumerate(candidates)}
    criteria = {
        key: (
            f"{c.get('display_name')}: at {', '.join(c.get('institutions') or []) or 'no listed institution'}; "
            f"works on {', '.join(c.get('topics') or []) or 'unknown topics'}; {c.get('works_count') or 0} works"
        )
        for key, c in options.items()
    }
    criteria[NOT_THEM] = "None of these authors is this professor, or the record can't tell them apart"
    question = Choice(
        instructions=(
            "Which OpenAlex author record is the professor? Match the department and research area to the "
            "author's topics and institution; a same-name author in another field is a different person."
        ),
        criteria=criteria,
    )
    state = {"professor": name, "school": school, "department or programme": programme or "unknown"}
    try:
        answer = await _ask(state, question)
    except Exception:  # noqa: BLE001 - no answer: the agent disambiguates
        return None
    choice = getattr(answer, "choice", None)
    if choice not in options or (getattr(answer, "confidence", None) or 0.0) < settings.typesafe_auto_accept:
        return None
    return options[choice]


#: Fit levels, low to high, as Jev sees them; the label is what the UI shows.
FIT_LEVELS = [
    ("unrelated", "The papers are about a different field or problem than the interests"),
    ("tangential", "Same broad field, but the papers' topics and methods don't touch the interests"),
    ("related", "The papers share a topic or method with the interests, though not their focus"),
    ("strong", "Several papers work directly on the problems the interests describe"),
    ("direct", "The professor's main line of work is what the interests describe"),
]
FIT_QUESTION = Score(
    instructions=(
        "How well does this professor's research, judged from their papers, fit the student's research "
        "interests? Judge the meaning of the work, not shared words."
    ),
    criteria=[description for _, description in FIT_LEVELS],
)
#: The level from which a fit counts as related: enough to keep a
#: professor the similarity score would drop.
RELATED_LEVEL = 2


def _fit_evidence(papers: list[dict], max_papers: int = 5, max_chars: int = 800) -> list[dict]:
    return [
        {"title": p.get("title") or "(untitled)", "abstract": (p.get("abstract") or "")[:max_chars]}
        for p in papers[:max_papers]
    ]


async def rate_fit(interest: str, papers: list[dict], user_id: str | None = None) -> dict | None:
    """{"level", "label", "score", "confidence"}: `level` is 0-4 (it can
    sit between levels), `score` the same as 0-1. None when off or
    unanswered. Pass the closest papers first; five are judged."""
    if not interest.strip() or not papers or not await _allowed(settings.typesafe_fit_rating, user_id):
        return None
    try:
        answer = await _ask({"interests": interest[:3000], "papers": _fit_evidence(papers)}, FIT_QUESTION)
    except Exception:  # noqa: BLE001 - no rating: the similarity stands alone
        return None
    level = float(getattr(answer, "score", 0.0) or 0.0)
    return {
        "level": round(level, 2),
        "label": FIT_LEVELS[min(round(level), len(FIT_LEVELS) - 1)][0],
        "score": round(level / (len(FIT_LEVELS) - 1), 4),
        "confidence": round(float(getattr(answer, "confidence", 0.0) or 0.0), 4),
    }
