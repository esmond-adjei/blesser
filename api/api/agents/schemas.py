from datetime import datetime

from pydantic import BaseModel


class AgentToolOut(BaseModel):
    name: str
    scope: str
    enabled: bool
    # Set in code, not by the account.
    read_only: bool
    confirm_required: bool
    description: str = ""
    group: str | None = None
    updated_at: datetime | None = None


class AgentToolGroupOut(BaseModel):
    id: str
    label: str
    description: str
    tools: list[str]


class AgentToolGroupUpdate(BaseModel):
    """PATCH semantics: only provided fields are written."""

    enabled: bool | None = None
    # Gradis only: ask before any member that changes something runs.
    confirm_required: bool | None = None


class AgentToolUpdate(BaseModel):
    """PATCH semantics: only provided fields are written."""

    enabled: bool | None = None
    confirm_required: bool | None = None


class AgentTaskOut(BaseModel):
    task_type: str
    enabled: bool
    tools: list[str] = []
    updated_at: datetime | None = None


class AgentTaskUpdate(BaseModel):
    """PATCH semantics; an empty tools list clears the allowlist."""

    enabled: bool | None = None
    tools: list[str] | None = None
