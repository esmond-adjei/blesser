from datetime import date, datetime

from pydantic import BaseModel, Field

from api.opportunities.models import (
    OpportunityCategory,
    OpportunityKind,
    OpportunityStatus,
)


class OpportunityOut(BaseModel):
    id: str
    title: str
    organization: str
    category: str
    kind: str
    summary: str
    eligibility: str
    benefits: str
    location: str
    countries: list[str] = []
    requirements: list[str] = []
    tags: list[str] = []
    deadline: str
    deadline_date: date | None = None
    rolling: bool
    link: str
    source_url: str
    status: str
    source: str
    verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # Computed against today (UTC): rolling, undated, or a deadline not yet passed.
    is_open: bool
    days_left: int | None = None


class OpportunityPage(BaseModel):
    items: list[OpportunityOut]
    total: int


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


class AgentOpportunityIn(BaseModel):
    """save_opportunity payload. Empty fields stay empty; nothing is guessed."""

    title: str = Field(min_length=3, max_length=300)
    organization: str = Field(default="", max_length=200)
    category: OpportunityCategory
    kind: OpportunityKind = OpportunityKind.other
    summary: str = Field(default="", max_length=2000)
    eligibility: str = Field(default="", max_length=2000)
    benefits: str = Field(default="", max_length=300)
    location: str = Field(default="", max_length=200)
    countries: list[str] = []
    requirements: list[str] = []
    tags: list[str] = []
    deadline: str = Field(default="", max_length=120)
    rolling: bool = False
    link: str = ""
    source_url: str = Field(min_length=8)


class OpportunityModerate(BaseModel):
    status: OpportunityStatus
