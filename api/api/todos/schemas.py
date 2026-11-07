from datetime import date, datetime

from pydantic import BaseModel, Field

from api.todos.models import TodoPriority


class TodoOut(BaseModel):
    id: str
    title: str
    notes: str
    due_date: date | None = None
    priority: str
    done: bool
    done_at: datetime | None = None
    position: int
    opportunity_id: str | None = None
    application_id: str | None = None
    # Shown beside the to-do so the list reads without a lookup.
    opportunity_title: str | None = None
    application_label: str | None = None
    created_at: datetime
    updated_at: datetime


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    notes: str = Field(default="", max_length=4000)
    due_date: date | None = None
    priority: TodoPriority = TodoPriority.normal
    opportunity_id: str | None = None
    application_id: str | None = None


class TodoUpdate(BaseModel):
    """PATCH semantics: only provided fields are written."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    notes: str | None = Field(default=None, max_length=4000)
    due_date: date | None = None
    priority: TodoPriority | None = None
    done: bool | None = None
    position: int | None = None


class CalendarFeedOut(BaseModel):
    url: str
    # webcal:// form, which most calendar apps open as "subscribe".
    webcal_url: str
    created_at: datetime
