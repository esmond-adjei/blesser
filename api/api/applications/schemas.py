from datetime import date, datetime

from pydantic import BaseModel, Field

from api.applications.models import ApplicationStatus


class RequirementItem(BaseModel):
    label: str
    done: bool = False


class ProfessorLink(BaseModel):
    name: str
    professor_id: str | None = None
    candidate_id: str | None = None
    school: str | None = None


class ApplicationOut(BaseModel):

    id: str
    school: str
    program: str
    degree_type: str
    location: str
    link: str
    requirements: list[RequirementItem] = []
    offer: str
    deadline: str
    deadline_date: date | None = None
    status: str
    professors: list[ProfessorLink] = []
    notes: str
    fee_waiver: bool
    fee_waiver_notes: str
    source: str
    run_id: str | None
    created_at: datetime
    updated_at: datetime
    # The matching school's picture, when one of the account's schools has this name.
    school_image_url: str | None = None


class ApplicationCreate(BaseModel):
    school: str = Field(min_length=1)
    program: str = ""
    degree_type: str = "phd"
    location: str = ""
    link: str = ""
    requirements: list[RequirementItem] = []
    offer: str = ""
    deadline: str = ""
    # Omitted: parsed from `deadline` when that is an unambiguous date.
    deadline_date: date | None = None
    status: ApplicationStatus = ApplicationStatus.wishlist
    professors: list[ProfessorLink] = []
    notes: str = ""
    fee_waiver: bool = False
    fee_waiver_notes: str = ""


class ApplicationUpdate(BaseModel):
    """PATCH semantics: only provided fields are written."""

    school: str | None = None
    program: str | None = None
    degree_type: str | None = None
    location: str | None = None
    link: str | None = None
    requirements: list[RequirementItem] | None = None
    offer: str | None = None
    deadline: str | None = None
    # Omitted while `deadline` changes: parsed from the new text.
    deadline_date: date | None = None
    status: ApplicationStatus | None = None
    professors: list[ProfessorLink] | None = None
    notes: str | None = None
    fee_waiver: bool | None = None
    fee_waiver_notes: str | None = None


class AgentApplicationIn(BaseModel):
    """save_application payload: school + notes required; other fields fill empty
    ones on upsert."""

    school: str = Field(min_length=1)
    program: str = ""
    degree_type: str = "phd"
    location: str = ""
    link: str = ""
    deadline: str = ""
    requirements: list[str] = []
    offer: str = ""
    fee_waiver: bool = False
    fee_waiver_notes: str = ""
    professors: list[str] = []
    notes: str = Field(min_length=1)
