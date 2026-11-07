"""Semantic Scholar: abstracts by DOI for works from ORCID or DBLP.

One batch call per professor; SEMANTIC_SCHOLAR_API_KEY raises the shared
limit. Unknown ids come back null and many abstracts are withheld.
"""

from __future__ import annotations

from api.core.config import settings
from api.prospects import source_http

BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
#: The API takes up to 500 ids a call; a professor's sample is far smaller.
MAX_IDS = 100


async def abstracts(dois: list[str]) -> dict[str, str]:
    """{lowercase doi: abstract}."""
    wanted = list(dict.fromkeys(d.strip().lower() for d in dois if d and d.strip()))[:MAX_IDS]
    if not wanted:
        return {}
    key = settings.semantic_scholar_api_key.strip()
    data = await source_http.request(
        "semantic_scholar",
        BATCH_URL,
        params={"fields": "externalIds,abstract"},
        body={"ids": [f"DOI:{d}" for d in wanted]},
        headers={"x-api-key": key} if key else None,
    )
    out: dict[str, str] = {}
    for paper in data.get("items") or []:
        if not isinstance(paper, dict) or not paper.get("abstract"):
            continue
        doi = str((paper.get("externalIds") or {}).get("DOI") or "").strip().lower()
        if doi:
            out[doi] = str(paper["abstract"]).strip()
    return out
