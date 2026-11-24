from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from api.opportunities.models import (
    OpportunityCategory,
    OpportunityKind,
)


class FacetCount(BaseModel):
    key: str
    count: int


class OpportunityFacets(BaseModel):
    """Open, published opportunities per category and kind, for filter chips."""

    categories: list[FacetCount]
    kinds: list[FacetCount]
    total: int
    closing_soon: int


class OpportunitySubmit(BaseModel):
    """Someone shares an opportunity they found; held for review unless auto-published."""

    title: str = Field(min_length=3, max_length=300)
    organization: str = Field(default="", max_length=200)
    category: OpportunityCategory
    kind: OpportunityKind = OpportunityKind.other
    summary: str = Field(default="", max_length=4000)
    eligibility: str = Field(default="", max_length=4000)
    benefits: str = Field(default="", max_length=300)
    location: str = Field(default="", max_length=200)
    countries: list[str] = []
    requirements: list[str] = []
    tags: list[str] = []
    deadline: str = Field(default="", max_length=120)
    deadline_date: date | None = None
    rolling: bool = False
    link: str = Field(min_length=8, max_length=2000)


def clipped(limit: int) -> BeforeValidator:
    """Shorten model-written prose to `limit` at a word break instead of rejecting it."""

    def clip(value):
        if isinstance(value, str) and len(value) > limit:
            return value[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"
        return value

    return BeforeValidator(clip)


class AgentOpportunityIn(BaseModel):
    """save_opportunity payload. Empty fields stay empty; nothing is guessed."""

    title: Annotated[str, clipped(300)] = Field(min_length=3, max_length=300)
    organization: Annotated[str, clipped(200)] = Field(default="", max_length=200)
    category: OpportunityCategory
    kind: OpportunityKind = OpportunityKind.other
    summary: Annotated[str, clipped(2000)] = Field(default="", max_length=2000)
    eligibility: Annotated[str, clipped(2000)] = Field(default="", max_length=2000)
    benefits: Annotated[str, clipped(300)] = Field(default="", max_length=300)
    location: Annotated[str, clipped(200)] = Field(default="", max_length=200)
    countries: list[str] = []
    requirements: list[str] = []
    tags: list[str] = []
    deadline: str = Field(default="", max_length=120)
    rolling: bool = False
    link: str = ""
    source_url: str = Field(min_length=8)
