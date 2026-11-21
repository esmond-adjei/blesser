"""The shape every Assistant tool shares.

A tool is a read (runs freely), a change or a delete (each waits for the member's
approval in the chat), or a question set (opens the questionnaire). Every change goes
through the same service code as the app, so the Assistant can never do more than the
member could do by hand.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Query = Annotated[str, StringConstraints(strip_whitespace=True, max_length=180)]
RequiredQuery = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)
]
RecordId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]

Kind = Literal["read", "change", "delete", "ask"]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemberLookup(ToolInput):
    query: Query = ""


@dataclass
class Proposal:
    """What the approval card shows, and the checked arguments it will apply."""

    summary: str
    arguments: dict
    note: str = ""
    # The approve button's label. Deletes use a red button.
    action: str = "Approve"


@dataclass
class Applied:
    """The outcome of an approved change."""

    # Handed back to the model so the reply can carry on.
    result: dict
    # Shown when the reply cannot carry on (no model configured).
    receipt: str
    # A card for the record this change created or touched, when it has a page.
    preview: dict | None = None


ReadFn = Callable[..., Awaitable[tuple[dict, int | None]]]
ProposeFn = Callable[..., Awaitable[Proposal]]
ApplyFn = Callable[..., Awaitable[Applied]]


@dataclass(frozen=True)
class Tool:
    name: str
    schema: type[ToolInput]
    description: str
    label: str
    kind: Kind
    read: ReadFn | None = None
    propose: ProposeFn | None = None
    apply: ApplyFn | None = None
    # Reading member data marks the chat private, which keeps web search off.
    private: bool = True
    # Opens no database session (web search).
    needs_session: bool = True
    tags: frozenset[str] = field(default_factory=frozenset)

    @property
    def changes(self) -> bool:
        return self.kind in ("change", "delete")


def record(row: dict, fields) -> dict:
    """Only the named fields that have a value, with long text trimmed."""
    return {
        key: value[:900] if isinstance(value, str) else value
        for key in fields
        if (value := row.get(key)) is not None
    }


def matching(rows, query, fields):
    terms = query.casefold().split()
    return [
        row
        for row in rows
        if all(
            term in " ".join(str(row.get(field, "")) for field in fields).casefold()
            for term in terms
        )
    ]


def preview(kind, row_id, title, detail="", url=None) -> dict:
    return {"kind": kind, "id": row_id, "title": title, "detail": detail, "url": url}


def show(value: Any) -> str:
    if value is None or value == "":
        return "Empty"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, date):
        return f"{value.day} {value:%b %Y}"
    if isinstance(value, list):
        if not value:
            return "None"
        return ", ".join(show(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {show(v)}" for k, v in value.items())
    text = str(value)
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            return show(date.fromisoformat(text))
        except ValueError:
            pass
    return " ".join(text.split())[:300]


def field_lines(values: dict, labels: dict[str, str] | None = None) -> str:
    """One "Label: value" line per field, for the approval card."""
    labels = labels or {}
    return "\n".join(
        f"{labels.get(key, key.replace('_', ' ').capitalize())}: {show(value)}"
        for key, value in values.items()
    )


def quoted(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    return f"“{text[: limit - 1]}…”" if len(text) > limit else f"“{text}”"
