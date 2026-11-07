import pytest

from api.candidates import scoring
from api.core.config import Settings


def _settings_for(provider: str) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        embedding_provider=provider,
        embedding_api_key="",
    )


def test_tfidf_fallback_scores_overlap():
    sims = scoring._tfidf_fallback_similarity(
        "mobile robotics reinforcement learning",
        [
            "mobile robotics and reinforcement learning for navigation",
            "medieval poetry",
        ],
    )
    assert sims[0] > sims[1]
    assert all(0.0 <= s <= 1.0 for s in sims)


def test_embed_and_score_local_needs_no_keys(monkeypatch):
    monkeypatch.setattr(scoring, "settings", _settings_for("local"))
    out = scoring.embed_and_score(
        "mobile robotics",
        ["mobile robotics navigation", "unrelated topic entirely"],
    )
    assert out["best_index"] == 0
    assert out["score"] > 0


def test_embed_and_score_empty_abstracts():
    out = scoring.embed_and_score("anything", ["", ""])  # type: ignore[list-item]
    assert out == {"score": 0.0, "best_index": None}


def test_embed_and_score_falls_back_without_keys(monkeypatch):
    monkeypatch.setattr(scoring, "settings", _settings_for("voyage"))
    out = scoring.embed_and_score("robotics", ["robotics paper", "cooking recipes"])
    assert out["best_index"] == 0
    assert "all_scores" in out


def test_unknown_embedding_provider_raises(monkeypatch):
    monkeypatch.setattr(scoring, "settings", _settings_for("nope"))
    with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
        scoring.embed_texts(["hello"])


def test_embedding_info_lists_supported():
    info = scoring.get_embedding_info()
    assert "voyage" in info["supported_providers"]
    assert "ollama" in info["supported_providers"]
    assert "gemini" in info["supported_providers"]
