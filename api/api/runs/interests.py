"""Interest suggestions for a new run, drawn from the user's CVs.

Every suggestion cites its excerpt; an LLM phrase citing no known excerpt is dropped.
Without a usable model, a deterministic pass lifts research and summary text.
"""

import json
import logging
import re

from api.agent.llm.factory import get_provider
from api.cv import markdown as cv_markdown
from api.cv import service as cv_service
from api.metering.service import metered
from api.providers import service as providers_service

log = logging.getLogger(__name__)

INTEREST_SECTIONS = ("summary", "research", "projects", "publications", "education")
MAX_DOCUMENTS = 5
MAX_UNITS = 60
MAX_UNIT_CHARS = 400
MAX_SUGGESTIONS = 8

SYSTEM_PROMPT = (
    "You extract research interests from a CV for a graduate-school search. "
    "Given numbered CV excerpts, return JSON only: "
    '{"interests": [{"text": "...", "unit": "<excerpt id>"}]}. '
    "Each text is a 3-10 word research interest phrase (methods or problem areas, "
    "not job titles), grounded in the cited excerpt. At most 8, most specific first. "
    "Never invent topics the excerpts do not support."
)


async def _collect_units(
    session, user_id: str, document_id: str | None = None
) -> tuple[list[dict], list[dict]]:
    """Interest-bearing excerpts from one CV (404 unless it is the user's), or the newest few."""
    if document_id:
        ids = [document_id]
    else:
        ids = [
            d["id"]
            for d in (await cv_service.list_documents(session, user_id, kind="cv"))[:MAX_DOCUMENTS]
        ]
    sources: list[dict] = []
    units: list[dict] = []
    for doc_id in ids:
        doc = await cv_service.get_document_or_404(session, doc_id, user_id)
        sources.append({"document_id": doc.id, "title": doc.title})
        n = 0
        for heading, body in cv_markdown.sections(doc.markdown or ""):
            section, _ = cv_markdown.section_hint(heading)
            if section not in INTEREST_SECTIONS:
                continue
            for block in re.split(r"\n\s*\n|\n(?=\s*[-*+] )", body):
                text = re.sub(r"^\s*[-*+]\s+", "", block).strip()
                text = re.sub(r"\s+", " ", text)
                if len(text) < 12:
                    continue
                n += 1
                units.append(
                    {
                        "id": f"{doc.id}:{n}",
                        "document_id": doc.id,
                        "document_title": doc.title,
                        "section": section,
                        "text": text[:MAX_UNIT_CHARS],
                    }
                )
                if len(units) >= MAX_UNITS:
                    return units, sources
    return units, sources


def _suggestion(text: str, unit: dict) -> dict:
    return {
        "text": text,
        "document_id": unit["document_id"],
        "document_title": unit["document_title"],
        "section": unit["section"],
        "evidence": unit["text"][:200],
    }


def _dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for item in items:
        key = re.sub(r"\W+", " ", item["text"].lower()).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out[:MAX_SUGGESTIONS]


def heuristic_suggestions(units: list[dict]) -> list[dict]:
    """First clause of each research/summary/projects excerpt."""
    ranked = sorted(
        units,
        key=lambda u: (
            "research",
            "summary",
            "projects",
            "publications",
            "education",
        ).index(u["section"]),
    )
    out = []
    for u in ranked:
        clause = re.split(r"(?<=[.;:])\s|\s[–—-]\s", u["text"], maxsplit=1)[0].strip(
            " .;:"
        )
        words = clause.split()
        if len(words) < 2:
            continue
        out.append(_suggestion(" ".join(words[:12]), u))
    return _dedupe(out)


def parse_llm_suggestions(raw: str, units: list[dict]) -> list[dict]:
    """Keep only phrases that cite a unit we actually sent."""
    by_id = {u["id"]: u for u in units}
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for item in data.get("interests") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        unit = by_id.get(str(item.get("unit") or ""))
        if unit and 2 <= len(text.split()) <= 14:
            out.append(_suggestion(text, unit))
    return _dedupe(out)


async def suggest_interests(session, user_id: str, document_id: str | None = None) -> dict:
    units, sources = await _collect_units(session, user_id, document_id)
    if not units:
        return {"sources": sources, "suggestions": [], "method": "none"}
    try:
        from api.billing import service as billing

        llm_kwargs = await providers_service.resolve_llm_kwargs(session, user_id)
        provider = metered(get_provider(**llm_kwargs), user_id, "suggestions")
        excerpts = "\n".join(f"[{u['id']}] ({u['section']}) {u['text']}" for u in units)
        messages = [{"role": "user", "content": excerpts}]
        reservation = await billing.reserve_model_call(
            user_id, llm_kwargs, billing.estimate_tokens(messages, SYSTEM_PROMPT, 800)
        )
        try:
            response = await provider.chat(
                messages=messages, system=SYSTEM_PROMPT, tools=[], max_tokens=800
            )
        finally:
            await billing.release(reservation)
        suggestions = parse_llm_suggestions(response.text or "", units)
        if suggestions:
            return {"sources": sources, "suggestions": suggestions, "method": "model"}
    except Exception as exc:  # noqa: BLE001 - suggestions degrade to the heuristic
        log.info("interest suggestions: model unavailable, using heuristic: %s", exc)
    return {
        "sources": sources,
        "suggestions": heuristic_suggestions(units),
        "method": "heuristic",
    }
