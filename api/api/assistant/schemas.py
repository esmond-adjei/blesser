from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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


Answer = (
    Annotated[str, StringConstraints(max_length=300)]
    | Annotated[
        list[Annotated[str, StringConstraints(max_length=300)]], Field(max_length=6)
    ]
)


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    # Leave out to skip the questions.
    answers: dict[str, Answer] | None = Field(default=None, max_length=4)


class ToolStep(BaseModel):
    kind: Literal["tool"] = "tool"
    tool: str
    label: str
    ok: bool
    note: str = ""


class Commentary(BaseModel):
    kind: Literal["commentary"] = "commentary"
    text: str


class Thought(BaseModel):
    kind: Literal["thought"] = "thought"
    text: str


TraceEntry = ToolStep | Commentary | Thought


class Source(BaseModel):
    key: str
    kind: Literal[
        "opportunity",
        "application",
        "todo",
        "project",
        "document",
        "answer",
        "web",
        "scan",
        "find",
        "site",
        "saved_search",
        "profile",
        "settings",
    ]
    id: str
    title: str
    detail: str = ""
    url: str | None = None
    opportunity: MemberOpportunity | None = None
    # A record this turn created, shown as a card that opens it.
    preview: bool = False


class Question(BaseModel):
    id: str
    prompt: str
    type: Literal["single", "multiple", "text", "date"]
    options: list[str] = []
    allow_other: bool = False
    max_choices: int | None = None
    required: bool = True


class PendingCall(BaseModel):
    """A change waiting for approval, or questions waiting for answers."""

    id: str
    type: Literal["change", "questions"] = "change"
    tool: str = ""
    summary: str
    trace: list[TraceEntry]
    note: str = ""
    # The approve button's label; danger shows it in red (deletes and stops).
    action: str = "Approve"
    tone: Literal["default", "danger"] = "default"
    questions: list[Question] = []


class MessageOut(APIModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: Literal["user", "assistant"]
    content: str
    trace: list[TraceEntry]
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
