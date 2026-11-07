"""Candidate tool implementations: deterministic alignment scoring."""

from api.agent.tools.context import ToolContext
from api.candidates import scoring
from api.core.config import settings

#: Best-matching works returned with a score, for the model to cite by exact title.
TOP_WORKS = 5

LEXICAL_NOTE = (
    "Lexical scoring only (no embedding model): the score counts shared "
    "words, so the same topic in different words can score 0. Judge "
    "relatedness from the top_works titles; never conclude no match from "
    "this score alone."
)


async def handle_score_alignment(tool_input: dict, ctx: ToolContext) -> dict:
    """score_alignment: cached interest vector, else full embed-and-score, else TF-IDF.

    With `openalex_id` the server scores that author's fetched works and returns
    the best titles, so the model needn't re-type abstracts."""
    from api.prospects import grounding

    works = None
    author_id = tool_input.get("openalex_id")
    if author_id:
        works = grounding.works_for(ctx, str(author_id))
        if not works:
            return {
                "error": (
                    "No fetched works for this openalex_id in this task. Call "
                    "get_author_works for it first, then score_alignment."
                )
            }
        texts = [(w.get("abstract") or w.get("title") or "").strip() for w in works]
        interest = tool_input.get("interest_text") or getattr(
            getattr(ctx, "run", None), "interest_statement", ""
        )
    else:
        texts = [a for a in tool_input.get("abstracts") or [] if (a or "").strip()]
        interest = tool_input.get("interest_text") or ""
    if not any(texts):
        # A score over nothing can never back a save; say what to send.
        return {
            "error": (
                "abstracts is empty. Pass the openalex_id you fetched works for, "
                "or the abstracts get_author_works returned (the title for any "
                "work without an abstract)."
            )
        }
    from api.billing import service as billing

    refusal = await billing.tool_call_refusal(
        ctx.user_id, "scoring", settings.embedding_provider, settings.embedding_model
    )
    if refusal is not None:
        return {"error": refusal}
    result = await scoring.score_interest_for_ctx_async(ctx, interest, texts)
    grounding.record_score(ctx, texts, result)
    method = result.get("method", "embedding")
    reading = {
        "method": method,
        "band": scoring.score_band(result.get("score"), method),
    }
    if method == "lexical":
        reading["note"] = LEXICAL_NOTE
    if works is None:
        return {**result, **reading}
    sims = [float(x) for x in result.get("all_scores", [])]
    ranked = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)
    # Another source's works: titles only (DBLP) or grant abstracts.
    candidate = (getattr(ctx, "author_candidates", None) or {}).get(
        grounding.author_key(str(author_id))
    ) or {}
    if candidate.get("confidence"):
        reading["confidence"] = candidate["confidence"]
    return {
        "openalex_id": author_id,
        "score": result.get("score"),
        **reading,
        "top_works": [
            {
                "title": works[i].get("title"),
                "year": works[i].get("year"),
                "score": round(sims[i], 4),
            }
            for i in ranked[:TOP_WORKS]
        ],
    }
