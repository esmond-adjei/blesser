"""ask_member: a short questionnaire the Assistant opens when a request is unclear."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from api.core.exceptions import BadRequestError

from .base import Tool, ToolInput

MAX_QUESTIONS = 4
MAX_ANSWER = 300

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Question(ToolInput):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")] = Field(
        description="A short snake_case key for the answer, unique in this set."
    )
    prompt: Annotated[Text, StringConstraints(max_length=200)]
    type: Literal["single", "multiple", "text", "date"]
    options: list[Annotated[Text, StringConstraints(max_length=80)]] = Field(
        default_factory=list,
        max_length=6,
        description="2 to 6 options for single and multiple. Leave empty for text and date.",
    )
    allow_other: bool = Field(
        default=False,
        description="For single and multiple: also offer a free text answer.",
    )
    max_choices: int | None = Field(default=None, ge=1, le=6)
    required: bool = True

    @model_validator(mode="after")
    def options_fit_type(self):
        choice = self.type in ("single", "multiple")
        if choice and not 2 <= len(self.options) <= 6:
            raise ValueError("Choice questions need 2 to 6 options")
        if not choice and (self.options or self.allow_other):
            raise ValueError("Only choice questions take options")
        if len({o.casefold() for o in self.options}) != len(self.options):
            raise ValueError("Options must be different")
        if self.max_choices is not None and self.type != "multiple":
            raise ValueError("max_choices is only for multiple choice")
        return self


class AskMember(ToolInput):
    title: Annotated[Text, StringConstraints(max_length=120)] = Field(
        description="One short sentence on why you are asking, shown as the questionnaire title."
    )
    questions: list[Question] = Field(min_length=1, max_length=MAX_QUESTIONS)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Question ids must be unique")
        return self


def _clean(value) -> str:
    if not isinstance(value, str):
        raise BadRequestError("Answer with text.")
    value = " ".join(value.split())
    if len(value) > MAX_ANSWER:
        raise BadRequestError(f"Keep each answer under {MAX_ANSWER} characters.")
    return value


def validate_answers(questions: list[dict], answers: dict) -> dict:
    """The member's answers, checked against the questions the Assistant asked."""
    known = {q["id"] for q in questions}
    if set(answers) - known:
        raise BadRequestError("Answer only the questions that were asked.")
    out = {}
    for q in (Question.model_validate(item) for item in questions):
        raw = answers.get(q.id)
        if raw in (None, "", []):
            if q.required:
                raise BadRequestError(f"Answer “{q.prompt}”.")
            continue
        if q.type == "multiple":
            if not isinstance(raw, list):
                raise BadRequestError(f"Choose one or more options for “{q.prompt}”.")
            values = [_clean(v) for v in raw]
            values = [v for i, v in enumerate(values) if v and v not in values[:i]]
            others = [v for v in values if v not in q.options]
            if others and (not q.allow_other or len(others) > 1):
                raise BadRequestError(f"Choose from the options for “{q.prompt}”.")
            if q.max_choices and len(values) > q.max_choices:
                raise BadRequestError(f"Choose up to {q.max_choices} for “{q.prompt}”.")
            if values:
                out[q.id] = values
        else:
            value = _clean(raw)
            if not value:
                if q.required:
                    raise BadRequestError(f"Answer “{q.prompt}”.")
                continue
            if q.type == "single" and value not in q.options and not q.allow_other:
                raise BadRequestError(f"Choose one of the options for “{q.prompt}”.")
            if q.type == "date":
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise BadRequestError(f"Pick a date for “{q.prompt}”.") from exc
            out[q.id] = value
    return out


def answers_text(questions: list[dict], answers: dict) -> str:
    """The answers as the member's own chat message."""
    lines = []
    for q in questions:
        value = answers.get(q["id"])
        if value in (None, "", []):
            continue
        if q["type"] == "date":
            day = date.fromisoformat(value)
            value = f"{day.day} {day:%B %Y}"
        if isinstance(value, list):
            value = ", ".join(value)
        lines.append(f"{q['prompt']}\n{value}")
    return "\n\n".join(lines)


TOOLS = [
    Tool(
        "ask_member",
        AskMember,
        "Open a short questionnaire when the request is unclear and a wrong guess would waste the member's time or allowance. Ask up to four short questions, prefer choices over free text, and do not ask what you can read with a tool. The member may skip; then decide sensibly or ask in plain text.",
        "Asked a few questions",
        "ask",
        private=False,
    ),
]
