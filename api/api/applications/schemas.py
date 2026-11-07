from datetime import date, datetime

from pydantic import BaseModel, Field

from api.applications.models import ApplicationStatus


class RequirementItem(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    done: bool = False


class ApplicationOut(BaseModel):
    id: str
    title: str
    organization: str
    kind: str
    location: str
    link: str
    benefits: str
    requirements: list[RequirementItem] = []
    deadline: str
    deadline_date: date | None = None
    status: str
    notes: str
    opportunity_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    organization: str = Field(default="", max_length=200)
    kind: str = Field(default="", max_length=60)
    location: str = Field(default="", max_length=200)
    link: str = Field(default="", max_length=2000)
    benefits: str = Field(default="", max_length=300)
    requirements: list[RequirementItem] = []
    deadline: str = Field(default="", max_length=120)
    # Omitted: parsed from `deadline` when that is an unambiguous date.
    deadline_date: date | None = None
    status: ApplicationStatus = ApplicationStatus.saved
    notes: str = Field(default="", max_length=20000)


class ApplicationUpdate(BaseModel):
    """PATCH semantics: only provided fields are written."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    organization: str | None = Field(default=None, max_length=200)
    kind: str | None = Field(default=None, max_length=60)
    location: str | None = Field(default=None, max_length=200)
    link: str | None = Field(default=None, max_length=2000)
    benefits: str | None = Field(default=None, max_length=300)
    requirements: list[RequirementItem] | None = None
    deadline: str | None = Field(default=None, max_length=120)
    # Omitted while `deadline` changes: parsed from the new text.
    deadline_date: date | None = None
    status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=20000)
