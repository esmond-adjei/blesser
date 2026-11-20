from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from api.opportunities.models import OpportunityCategory, OpportunityKind

Alerts = Literal["off", "daily", "weekly"]
Level = Literal["undergraduate", "masters", "phd", "postdoc", "founder"]
Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class MatchProfileIn(BaseModel):
    """What the member is looking for. Unknown countries are dropped."""

    model_config = ConfigDict(extra="forbid")

    categories: list[OpportunityCategory] = Field(default_factory=list, max_length=3)
    kinds: list[OpportunityKind] = Field(default_factory=list, max_length=12)
    fields: list[Term] = Field(default_factory=list, max_length=12)
    levels: list[Level] = Field(default_factory=list, max_length=5)
    countries: list[Term] = Field(default_factory=list, max_length=10)
    alerts: Alerts = "daily"
    closing_soon: bool = True


class MatchProfileOut(BaseModel):
    """`saved` is false while the values are only a suggestion from the Applicant Kit."""

    saved: bool
    categories: list[str]
    kinds: list[str]
    fields: list[str]
    levels: list[str]
    countries: list[str]
    alerts: Alerts
    closing_soon: bool
    updated_at: datetime | None


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    category: OpportunityCategory | None = None
    kind: OpportunityKind | None = None
    country: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    closing_within: int | None = Field(default=None, ge=0, le=365)


class SavedSearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    filters: SearchFilters
    alerts: Alerts = "daily"


class SavedSearchPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None
    alerts: Alerts | None = None


class SavedSearchOut(BaseModel):
    id: str
    name: str
    filters: SearchFilters
    alerts: Alerts
    created_at: datetime
