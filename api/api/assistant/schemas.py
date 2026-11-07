"""Gradis chat schemas."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _known_mode(value: str) -> str:
    """A turn's mode must be one of the bundles in api/assistant/modes.py."""
    from api.assistant.modes import MODES

    if value not in MODES:
        raise ValueError(f"mode must be one of: {', '.join(MODES)}")
    return value


class TextAttachment(BaseModel):
    kind: Literal["text"]
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=20000)


class ImageAttachment(BaseModel):
    kind: Literal["image"]
    name: str = Field(min_length=1, max_length=200)
    data_url: str = Field(max_length=2800000, pattern=r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$")
    thumb_url: str | None = Field(default=None, max_length=60000, pattern=r"^data:image/jpeg;base64,[A-Za-z0-9+/]+={0,2}$")


class ContextChip(BaseModel):
    """A composer chip the prompt went out with, as the user saw it. Kept
    on the message for display only; the model reads the ids above."""

    key: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=60)
    detail: str | None = Field(default=None, max_length=200)


class UiContext(BaseModel):
    """What the user is looking at. Sent by the webapp with each turn so
    Gradis can resolve 'this one' and tailor answers to the current view."""

    page: str = Field(default="", max_length=500)
    run_id: str | None = None
    candidate_id: str | None = None
    application_id: str | None = None
    draft_id: str | None = None
    document_id: str | None = None
    cv_version_id: str | None = None
    selection: str | None = Field(default=None, max_length=5000)
    attachments: list[TextAttachment | ImageAttachment] = Field(default_factory=list, max_length=3)
    chips: list[ContextChip] = Field(default_factory=list, max_length=12)


class ChatModelOverride(BaseModel):
    """Per-message model pick from the chat picker. A configured provider
    id uses that registry row; "system" forces the environment fallback;
    omitted means the active row (auto)."""

    provider: str = Field(min_length=1, max_length=64)
    effort: Literal["low", "medium", "high", "xhigh"] | None = None


class QueuePrompt(BaseModel):
    """A prompt the student sent while the agent was working."""

    content: str = Field(min_length=1, max_length=10000)
    # Urgent: hand it to the running turn instead of waiting for it.
    urgent: bool = False


class QueueUpdate(BaseModel):
    urgent: bool


class ConversationOut(BaseModel):
    id: str
    title: str
    preview: str | None = None
    message_count: int = 0
    has_pending: bool = False
    created_at: object | None = None
    updated_at: object | None = None


class ChatStreamRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    context: UiContext | None = None
    model: ChatModelOverride | None = None
    # Re-run a failed turn, reusing its unanswered user message if it was stored.
    retry: bool = False
    # Replace this user message and drop everything after it (edit-and-resend, regenerate).
    replace_message_id: str | None = Field(default=None, max_length=64)
    # Continue a turn that died after its call was approved, without resending.
    continue_turn: bool = False
    # How much the agent may do this turn: chat or agent.
    mode: str = "agent"

    _mode = field_validator("mode")(_known_mode)


class ConfirmRequest(BaseModel):
    call_id: str = Field(min_length=1)
    approved: bool
    context: UiContext | None = None
    model: ChatModelOverride | None = None
    # The mode the rest of the turn runs in once the call is answered.
    mode: str = "agent"

    _mode = field_validator("mode")(_known_mode)


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)
