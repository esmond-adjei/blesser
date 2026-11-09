from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer

from api.opportunities.schemas import OpportunitySubmit


class APIModel(BaseModel):
    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_datetime(self, value):
        if isinstance(value, datetime):
            return (
                (value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC))
                .isoformat()
                .replace("+00:00", "Z")
            )
        return value


class PublicOpportunity(APIModel):
    id: str
    slug: str
    title: str
    organization: str
    category: str
    kind: str
    summary: str
    eligibility: str
    benefits: str
    location: str
    countries: list[str]
    requirements: list[str]
    tags: list[str]
    deadline: str
    deadline_date: date | None
    rolling: bool
    link: str
    source_url: str
    verified_at: datetime | None
    published_at: datetime | None
    is_open: bool
    days_left: int | None
    closed: bool


class PublicPage(APIModel):
    items: list[PublicOpportunity]
    total: int


class Submission(OpportunitySubmit):
    email: EmailStr | None = None


class ReportIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    email: EmailStr | None = None


class Announcement(BaseModel):
    text: str = Field(max_length=1000)
    link: str = Field(max_length=2000)
    starts_on: date | None = None
    ends_on: date | None = None


class SiteContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hero_title: str = Field(default="Find your next opportunity", max_length=300)
    hero_subtitle: str = Field(default="", max_length=1000)
    announcement: Announcement | None = None


class CollectionOut(BaseModel):
    id: str
    slug: str
    title: str
    intro: str
    audience: str
    filter: dict | None
    item_ids: list[str]
    position: int
    published: bool


class PublicCollection(CollectionOut):
    items: list[PublicOpportunity]


class PublicSite(BaseModel):
    content: SiteContent
    featured: list[PublicOpportunity]
    closing_soon: list[PublicOpportunity]
