from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.app.schemas import MemberOpportunity
from api.opportunities.models import (
    OpportunityCategory,
    OpportunityKind,
    OpportunityStatus,
)
from api.public.schemas import APIModel
from api.scans.routes import ScheduleOut

Audience = Literal["public", "members"]
ReviewReason = Literal[
    "new_submission", "agent_find", "reported", "source_changed", "no_official_link"
]


class AuditEntry(APIModel):
    id: str
    actor_id: str
    actor_email: str
    action: str
    entity_type: str
    entity_id: str
    before: dict | None
    after: dict | None
    at: datetime


class AdminOpportunity(MemberOpportunity):
    status: OpportunityStatus
    review_reason: ReviewReason | None
    editor_note: str
    featured_rank: int | None
    source: str
    scan_id: str | None
    created_by: str | None
    published_by: str | None
    updated_at: datetime
    dedupe_key: str
    checked_at: datetime | None = None
    check_outcome: str = ""
    found_via_url: str = ""


class AdminDetail(AdminOpportunity):
    history: list[AuditEntry]
    trace_excerpt: str | None


class AdminPage(APIModel):
    items: list[AdminOpportunity]
    total: int


class OpportunityEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
    link: str = Field(default="", max_length=2000)
    source_url: str = Field(default="", max_length=2000)
    verified_at: datetime | None = None
    status: OpportunityStatus = OpportunityStatus.draft
    audience: Audience = "members"
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    featured_rank: int | None = None
    editor_note: str = Field(default="", max_length=10000)
    review_reason: ReviewReason | None = None
    published_at: datetime | None = None
    published_by: str | None = None

    @field_validator("verified_at", "published_at")
    @classmethod
    def utc_datetime(cls, value):
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value


class OpportunityPatch(OpportunityEdit):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    category: OpportunityCategory | None = None

    @model_validator(mode="after")
    def required_values(self):
        for field in self.model_fields_set - {
            "deadline_date",
            "verified_at",
            "featured_rank",
            "review_reason",
            "published_at",
            "published_by",
        }:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class BulkIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)
    action: Literal["publish_public", "publish_members", "archive", "hide", "to_review"]


class MergeIn(BaseModel):
    into_id: str


class DuplicatePair(APIModel):
    first: AdminOpportunity
    second: AdminOpportunity
    score: float
    reason: Literal["similar_title", "same_page"]


class DismissIn(BaseModel):
    first_id: str
    second_id: str


class AliasIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str = Field(min_length=1, max_length=200)
    canonical: str = Field(min_length=1, max_length=200)


class AliasOut(APIModel):
    alias: str
    canonical: str


class CollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(
        min_length=1, max_length=300, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    title: str = Field(min_length=1, max_length=300)
    intro: str = Field(default="", max_length=4000)
    audience: Audience = "public"
    filter: dict | None = None
    item_ids: list[str] = Field(default_factory=list, max_length=500)
    position: int = 0
    published: bool = False


class CollectionPatch(CollectionCreate):
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    title: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def required_values(self):
        for field in self.model_fields_set - {"filter"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class PublishingDefault(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: OpportunityStatus
    audience: Audience = "members"


class CommunityDefault(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: OpportunityStatus = OpportunityStatus.in_review


class ScanLimits(BaseModel):
    per_hour: int = Field(default=3, ge=0, le=1000)
    per_day: int = Field(default=10, ge=0, le=10000)


class CrawlerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours: int = Field(default=6, ge=0, le=8760)
    max_sources: int = Field(default=12, ge=1, le=100)
    max_items_per_source: int = Field(default=40, ge=1, le=200)
    max_candidates_per_task: int = Field(default=8, ge=0, le=100)
    host_interval_seconds: float = Field(default=2, ge=0.5, le=60)
    page_cache_seconds: int = Field(default=21600, ge=60, le=604800)


class FreshnessSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recheck_days: int = Field(default=30, ge=1, le=365)
    closing_days: int = Field(default=7, ge=0, le=60)
    closing_recheck_days: int = Field(default=14, ge=1, le=365)
    cycle_days: int = Field(default=30, ge=1, le=365)
    stale_days: int = Field(default=120, ge=7, le=1095)
    max_checks: int = Field(default=10, ge=0, le=200)
    max_agent_checks: int = Field(default=20, ge=0, le=1000)


class ScheduledScanSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_max: int = Field(default=3, ge=0, le=20)
    runs_per_hour: int = Field(default=10, ge=0, le=200)
    # Model tokens scheduled runs may use per day (UTC); 0 means no budget.
    daily_token_budget: int = Field(default=0, ge=0, le=1_000_000_000)


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_default: PublishingDefault = PublishingDefault(
        status=OpportunityStatus.published
    )
    community_default: CommunityDefault = CommunityDefault()
    auto_archive: bool = True
    member_scan_limits: ScanLimits = ScanLimits()
    scheduled_scans: ScheduledScanSettings = ScheduledScanSettings()
    crawler: CrawlerSettings | None = None
    freshness: FreshnessSettings | None = None
    aggregators: list[str] | None = Field(default=None, max_length=500)
    official_backfill: bool = False

    @field_validator("aggregators")
    @classmethod
    def aggregator_hosts(cls, value):
        if value is None:
            return None
        from api.opportunities.official import clean_hosts

        return clean_hosts(value)


class StaffUser(APIModel):
    id: str
    email: str
    display_name: str | None
    role: Literal["member", "editor", "admin"]
    email_verified: bool
    disabled: bool
    created_at: datetime
    scans_last_30_days: int


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["member", "editor", "admin"] | None = None
    disabled: bool | None = None


class UserPage(APIModel):
    items: list[StaffUser]
    total: int


class AuditPage(APIModel):
    items: list[AuditEntry]
    total: int


class ReportPatch(BaseModel):
    resolved: Literal[True]


class ReportOut(APIModel):
    id: str
    opportunity_id: str
    reason: str
    email: str | None
    resolved: bool
    created_at: datetime


class StaffSession(BaseModel):
    access_token: str
    refresh_token: str
    user: StaffUser


class StaffScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="", max_length=80)
    categories: list[OpportunityCategory] = Field(min_length=1, max_length=3)
    region: str = Field(default="", max_length=120)
    focus: str = Field(default="", max_length=2000)
    interval_hours: Literal[24, 72, 168] = 168
    paused: bool = False


class StaffSchedulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=80)
    categories: list[OpportunityCategory] | None = Field(
        default=None, min_length=1, max_length=3
    )
    region: str | None = Field(default=None, max_length=120)
    focus: str | None = Field(default=None, max_length=2000)
    interval_hours: Literal[24, 72, 168] | None = None
    paused: bool | None = None


class StaffSchedulesOut(BaseModel):
    schedules: list[ScheduleOut]
    member_schedules: int
    member_schedules_active: int
    runs_last_7_days: int
    tokens_today: int
    run_as: str | None
    intervals: list[int]
