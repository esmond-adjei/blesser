from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from api.app.schemas import MemberOpportunity
from api.public.schemas import APIModel

ChatText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
ChatTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: ChatText


class RenameRequest(BaseModel):
    title: ChatTitle


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    approved: bool


class ToolStep(BaseModel):
    tool: str
    label: str
    ok: bool
    note: str = ""


class Source(BaseModel):
    key: str
    kind: Literal[
        "opportunity", "application", "todo", "project", "document", "answer", "web"
    ]
    id: str
    title: str
    detail: str = ""
    url: str | None = None
    opportunity: MemberOpportunity | None = None


class PendingCall(BaseModel):
    id: str
    summary: str
    trace: list[ToolStep]
    note: str = ""


class MessageOut(APIModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: Literal["user", "assistant"]
    content: str
    trace: list[ToolStep]
    sources: list[Source]
    cited_deadlines: bool
    created_at: datetime


class ChatOut(APIModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    running: bool
    pending_call: PendingCall | None


class ChatDetail(ChatOut):
    messages: list[MessageOut]
