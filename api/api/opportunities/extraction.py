import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.agent.llm.factory import get_provider
from api.agent.orchestrator import _add_usage, _chat_with_retry
from api.agent.untrusted import UNTRUSTED_CONTENT_RULE
from api.core.config import settings
from api.opportunities.page_content import Page, deadline_dates
from api.opportunities.schemas import AgentOpportunityIn


class ExtractedOpportunity(AgentOpportunityIn):
    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def complete_fields(cls, value):
        if isinstance(value, dict) and (
            missing := cls.model_fields.keys() - value.keys()
        ):
            raise ValueError("Missing extraction fields: " + ", ".join(sorted(missing)))
        return value


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    relevant: bool
    region_eligible: bool
    reason: str = Field(max_length=500)
    confidence: float = Field(ge=0, le=1)
    opportunity: ExtractedOpportunity | None


def extraction_schema() -> dict:
    schema = Extraction.model_json_schema()

    def strict(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                strict(value)
        elif isinstance(node, list):
            for value in node:
                strict(value)

    strict(schema)
    return schema


def trimmed_text(page: Page) -> str:
    limit = settings.extraction_max_chars
    if len(page.text) <= limit:
        return page.text
    lines = page.text.splitlines()
    signals = [
        line
        for line in lines
        if any(
            key in line.lower()
            for key in (
                "deadline",
                "eligib",
                "apply",
                "ghana",
                "africa",
                "rolling",
                "funding",
                "scholarship",
            )
        )
    ]
    tail = "\n".join(signals)[: limit // 2]
    return page.text[: limit - len(tail)] + "\n" + tail


async def extract_page(
    page: Page, *, category: str, region: str, today: str
) -> Extraction:
    from api.core.db import SessionLocal
    from api.opportunities.crawl_models import PageCache

    cache_key = (
        f"v1:{settings.llm_provider}:{settings.llm_model}:{region.strip().casefold()}"
    )
    async with SessionLocal() as session:
        row = await session.get(PageCache, page.url)
        cached = (
            row.metadata_json.get("extractions", {}).get(cache_key)
            if row and row.content_hash == page.content_hash
            else None
        )
    if cached:
        return Extraction.model_validate_json(json.dumps(cached))
    schema = extraction_schema()
    response = await _chat_with_retry(
        get_provider(),
        [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "url": page.url,
                        "preferred_category": category,
                        "region": region,
                        "today": today,
                        "title": page.title,
                        "deadline_dates": [
                            d.isoformat()
                            for d in deadline_dates(page.text, page.metadata)
                        ],
                        "page_text": trimmed_text(page),
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "Extract one named, currently open opportunity from the supplied page. Call extract_opportunity exactly once. relevant=false means a generic page, a closed call or no opportunity anywhere. region_eligible=false means a real opportunity excludes the target region. Assign the actual audience category even when it differs from preferred_category. Never invent facts. Use ISO deadline only when stated, empty strings or lists for missing fields. source_url must equal the supplied URL. Preserve country restrictions. confidence measures certainty of openness, eligibility and fields. "
        + UNTRUSTED_CONTENT_RULE,
        [
            {
                "name": "extract_opportunity",
                "description": "Return the page extraction.",
                "parameters": schema,
                "strict": True,
            }
        ],
        0,
    )
    _add_usage(response.usage, 0)
    if response.truncated:
        raise ValueError("extraction truncated")
    if response.tool_calls:
        if (
            len(response.tool_calls) != 1
            or response.tool_calls[0].name != "extract_opportunity"
        ):
            raise ValueError("expected one extraction")
        result = Extraction.model_validate_json(
            json.dumps(response.tool_calls[0].arguments)
        )
    else:
        result = Extraction.model_validate_json(response.text)
    async with SessionLocal() as session:
        row = await session.get(PageCache, page.url, with_for_update=True)
        if row and row.content_hash == page.content_hash:
            metadata = dict(row.metadata_json)
            metadata["extractions"] = {
                **metadata.get("extractions", {}),
                cache_key: result.model_dump(mode="json"),
            }
            row.metadata_json = metadata
            await session.commit()
    return result
