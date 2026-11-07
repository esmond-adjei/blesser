"""Deterministic alignment scoring, deliberately kept out of the LLM's hands.

Scores are cosine similarity over embeddings (EMBEDDING_PROVIDER), so they're
comparable and reproducible. `local` is a keyless TF-IDF fallback for dev.
"""

import asyncio
import hashlib
import re
from array import array

import numpy as np

from api.core.config import settings
from api.core.ttlcache import TTLCache

_voyage_client = None
_openai_embed_client: tuple[str, str | None, object] | None = None

PROVIDER_DEFAULT_EMBEDDING_MODELS = {
    "voyage": "voyage-3"
    if settings.embedding_model is None
    else settings.embedding_model,
    "openai": "text-embedding-3-small",
    "ollama": "nomic-embed-text",
    "gemini": "gemini-embedding-001",
    "openai-compatible": "text-embedding-3-small",
    "local": "tfidf",
}

SUPPORTED_EMBEDDING_PROVIDERS = sorted(PROVIDER_DEFAULT_EMBEDDING_MODELS)


def get_embedding_info() -> dict:
    provider = (settings.embedding_provider or "voyage").lower().strip()
    model = settings.embedding_model or PROVIDER_DEFAULT_EMBEDDING_MODELS.get(
        provider, ""
    )
    base_url = settings.embedding_base_url
    if provider == "ollama" and not base_url:
        base_url = "http://localhost:11434/v1"
    if provider == "gemini" and not base_url:
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    return {
        "embedding_provider": provider,
        # Without an embedding backend every score is word overlap.
        "scoring_method": (
            "lexical"
            if provider == "local" or not settings.resolve_embedding_api_key()
            else "embedding"
        ),
        "embedding_model": model,
        "embedding_base_url": base_url,
        "supported_providers": SUPPORTED_EMBEDDING_PROVIDERS,
    }


def _get_voyage_client():
    global _voyage_client
    if _voyage_client is None and settings.resolve_embedding_api_key():
        import voyageai

        _voyage_client = voyageai.Client(  # pyright: ignore[reportPrivateImportUsage]
            api_key=settings.resolve_embedding_api_key()
        )
    return _voyage_client


def _get_openai_embed_client(api_key: str, base_url: str | None):
    """Cached client: rebuilding it per call paid a fresh TLS handshake each time."""
    global _openai_embed_client
    if _openai_embed_client is not None:
        cached_key, cached_url, client = _openai_embed_client
        if cached_key == api_key and cached_url == base_url:
            return client
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "The `openai` package is required for openai/ollama/gemini/openai-compatible "
            "embeddings. Run `uv sync` / `pip install openai`."
        ) from exc
    kwargs: dict = {"api_key": api_key or "not-needed"}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    _openai_embed_client = (api_key, base_url, client)
    return client


def _openai_compatible_embed(
    texts: list[str], model: str, api_key: str, base_url: str | None
) -> list[list[float]]:
    client = _get_openai_embed_client(api_key, base_url)
    result = client.embeddings.create(input=texts, model=model)
    return [list(d.embedding) for d in result.data]


#: Vectors per (provider, model, endpoint, text); float32 keeps an entry near 4 KB.
_VECTORS: TTLCache[array] = TTLCache(4096, lambda: settings.embedding_cache_seconds)


def _vector_key(text: str, input_type: str = "query") -> str:
    where = "|".join(
        (
            (settings.embedding_provider or "voyage").lower().strip(),
            settings.embedding_model or "",
            settings.embedding_base_url or "",
            input_type,
        )
    )
    return f"{where}|{hashlib.sha256(text.encode()).hexdigest()}"


def embed_texts(texts: list[str], input_type: str = "query") -> list[list[float]] | None:
    """Embed texts, sending only those not cached. `input_type` is "query" for the
    interest statement and "document" for abstracts (Voyage embeds them
    differently). Returns None with no API key (caller falls back to TF-IDF).
    """
    if not texts:
        return _embed_uncached(texts, input_type)
    keys = [_vector_key(t, input_type) for t in texts]
    found = [_VECTORS.get(k) for k in keys]
    missing = [i for i, v in enumerate(found) if v is None]
    if missing:
        fresh = _embed_uncached([texts[i] for i in missing], input_type)
        if fresh is None:
            return None
        for i, vector in zip(missing, fresh, strict=True):
            found[i] = array("f", vector)
            _VECTORS.put(keys[i], found[i])
    return [list(v) for v in found if v is not None]


def _embed_uncached(texts: list[str], input_type: str = "query") -> list[list[float]] | None:
    provider = (settings.embedding_provider or "voyage").lower().strip()
    if provider == "local":
        return None
    if provider == "voyage":
        if not settings.resolve_embedding_api_key():
            return None
        client = _get_voyage_client()
        if client is None:
            return None
        model = settings.embedding_model or PROVIDER_DEFAULT_EMBEDDING_MODELS["voyage"]
        result = client.embed(texts, model=model, input_type=input_type)
        return [list(e) for e in result.embeddings]
    if provider in ("openai", "ollama", "gemini", "openai-compatible"):
        api_key = settings.resolve_embedding_api_key()
        if not api_key:
            return None
        model = settings.embedding_model or PROVIDER_DEFAULT_EMBEDDING_MODELS[provider]
        base_url = settings.embedding_base_url
        if provider == "ollama" and not base_url:
            base_url = "http://localhost:11434/v1"
        if provider == "gemini" and not base_url:
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        return _openai_compatible_embed(texts, model, api_key, base_url)
    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER={provider!r}. Supported: {', '.join(SUPPORTED_EMBEDDING_PROVIDERS)}"
    )


def _tfidf_fallback_similarity(query: str, documents: list[str]) -> list[float]:
    """Crude keyless fallback for development; not real matching quality."""

    def tokenize(text: str) -> set[str]:
        return set(re.findall(r"[a-z]{3,}", text.lower()))

    q_tokens = tokenize(query)
    scores = []
    for doc in documents:
        d_tokens = tokenize(doc)
        if not q_tokens or not d_tokens:
            scores.append(0.0)
            continue
        overlap = len(q_tokens & d_tokens)
        scores.append(overlap / (len(q_tokens) ** 0.5 * len(d_tokens) ** 0.5))
    return scores


def _cosine_sims(query_vec, doc_vecs) -> list[float]:
    sims = (
        doc_vecs
        @ query_vec
        / (np.linalg.norm(doc_vecs, axis=1) * np.linalg.norm(query_vec) + 1e-9)
    )
    return sims.tolist()


def score_with_vector(query_vec: list[float], abstracts: list[str]) -> dict | None:
    """Score abstracts against a precomputed interest vector; None when they can't
    be embedded."""
    abstracts = [a for a in abstracts if a]
    if not abstracts:
        return {"score": 0.0, "best_index": None}

    try:
        vecs = embed_texts(abstracts, input_type="document")
    except Exception:  # noqa: BLE001 - fall back to full embed_and_score
        return None
    if vecs is None:
        return None

    try:
        # The cache can disagree with fresh vectors (model changed, corrupt value):
        # a mismatch must degrade to fallback, never fail the task.
        sims = _cosine_sims(
            np.array(query_vec, dtype=float), np.array(vecs, dtype=float)
        )
    except Exception:  # noqa: BLE001 - ValueError/UFuncTypeError on mismatch
        return None
    best_index = int(np.argmax(sims))
    return {
        "score": round(float(max(sims)), 4),
        "best_index": best_index,
        "all_scores": sims,
        "method": "embedding",
    }


def score_interest(
    interest_text: str,
    abstracts: list[str],
    cached_vector: list[float] | None = None,
) -> dict:
    """Cached interest vector, else full embed_and_score, else TF-IDF. Never raises
    on a corrupt cache."""
    if cached_vector is not None:
        scored = score_with_vector(cached_vector, abstracts)
        if scored is not None:
            return scored
    return embed_and_score(interest_text, abstracts)


async def score_interest_for_ctx_async(
    ctx, interest_text: str, abstracts: list[str]
) -> dict:
    """score_interest off the event loop (sync embedding SDKs). The interest vector
    is read before the hop so the thread never touches the ORM session."""
    from api.agent.tools.context import cached_interest_vector

    cached = cached_interest_vector(ctx)
    return await asyncio.to_thread(
        score_interest, interest_text, abstracts, cached
    )


def embed_and_score(interest_text: str, abstracts: list[str]) -> dict:
    """Overall alignment score plus the best-matching abstract's index. Uses max
    similarity, not mean: one strongly aligned paper is the better signal.
    """
    abstracts = [a for a in abstracts if a]
    if not abstracts:
        return {"score": 0.0, "best_index": None}

    vecs = None
    try:
        query = embed_texts([interest_text])
        docs = embed_texts(abstracts, input_type="document") if query is not None else None
        vecs = query + docs if query is not None and docs is not None else None
    except Exception:  # noqa: BLE001 - embedding backend failure falls back to TF-IDF
        vecs = None

    if vecs is not None:
        arr = np.array(vecs)
        query_vec, doc_vecs = arr[0], arr[1:]
        sims = _cosine_sims(query_vec, doc_vecs)
        method = "embedding"
    else:
        sims = _tfidf_fallback_similarity(interest_text, abstracts)
        method = "lexical"

    best_index = int(np.argmax(sims))
    return {
        "score": round(float(max(sims)), 4),
        "best_index": best_index,
        "all_scores": sims,
        "method": method,
    }


#: Rough reading of a score per method, highest first. Starting points to tune
#: against reviewed runs, not a calibration.
SCORE_BANDS: dict[str, tuple[tuple[float, str], ...]] = {
    "embedding": ((0.45, "strong"), (0.30, "moderate"), (0.15, "weak")),
    "lexical": ((0.25, "strong"), (0.08, "moderate"), (0.0001, "weak")),
}


def score_band(score: float | None, method: str | None) -> str:
    """strong / moderate / weak, or `unrelated` (embedding) / `no_overlap`
    (lexical: shares no words, which doesn't mean unrelated)."""
    bands = SCORE_BANDS.get(method or "embedding", SCORE_BANDS["embedding"])
    for floor, name in bands:
        if score is not None and score >= floor:
            return name
    return "no_overlap" if method == "lexical" else "unrelated"
