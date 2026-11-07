import asyncio


def test_score_by_id_without_a_run_on_the_context(monkeypatch):
    from types import SimpleNamespace

    from api.candidates import scoring
    from api.candidates import tools as candidate_tools
    from api.prospects import grounding

    ctx = SimpleNamespace(user_id=None)
    grounding.record_works(ctx, "A1", [{"title": "A paper", "abstract": "Text."}])

    async def score(ctx, interest_text, texts):
        assert interest_text == ""
        return {"score": 0.4, "best_index": 0, "all_scores": [0.4], "method": "embedding"}

    monkeypatch.setattr(scoring, "score_interest_for_ctx_async", score)
    out = asyncio.run(candidate_tools.handle_score_alignment({"openalex_id": "A1"}, ctx))
    assert out["score"] == 0.4
