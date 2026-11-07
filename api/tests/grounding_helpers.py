"""Record what the research tools would have returned so direct save_professor_record calls pass the grounding gate."""

from api.prospects import grounding


def ground(ctx, payload: dict, institution: str | None = None) -> dict:
    """Mutates and returns `payload` (adds an openalex_id when missing)."""
    openalex_id = payload.setdefault("openalex_id", f"A-{payload['name']}")
    grounding.record_author_candidates(
        ctx, [{"openalex_id": openalex_id, "institution": institution}]
    )
    works = [
        {
            "title": p["title"],
            "abstract": p.get("abstract"),
            "year": p.get("year"),
            "url": p.get("url"),
        }
        for p in payload.get("papers", [])
    ]
    grounding.record_works(ctx, openalex_id, works)
    texts = [w["abstract"] or w["title"] for w in works]
    grounding.record_score(ctx, texts, {"score": payload["similarity_score"]})
    return payload
