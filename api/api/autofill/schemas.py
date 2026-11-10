from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.applicant_kit.schemas import URL

Short = Annotated[str, Field(max_length=500)]
Text = Annotated[str, Field(max_length=4000)]
Key = Annotated[str, Field(min_length=1, max_length=200)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Page(Input):
    url: URL
    title: Short = ""
    host: Annotated[str, Field(max_length=253)] = ""

    @model_validator(mode="after")
    def nonempty_url(self):
        if not self.url:
            raise ValueError("Page URL is required")
        return self


class Use(Input):
    profile: bool = True
    project_id: Annotated[str, Field(min_length=1, max_length=100)] | None = None


class Option(Input):
    value: Short
    label: Short


class FormField(Input):
    key: Key
    tag: Literal["input", "textarea", "select", "contenteditable"] = "input"
    type: Annotated[str, Field(max_length=50)] = "text"
    name: Short = ""
    id: Short = ""
    autocomplete: Short = ""
    label: Text = ""
    placeholder: Short = ""
    help_text: Text = ""
    section: Short = ""
    options: list[Option] = Field(default_factory=list, max_length=500)
    required: bool = False
    max_length: Annotated[int, Field(ge=0, le=1000000)] | None = None
    word_limit: Annotated[int, Field(ge=0, le=100000)] | None = None
    accept: Short = ""


class FillRequest(Input):
    page: Page
    use: Use = Field(default_factory=Use)
    fields: list[FormField] = Field(max_length=300)
    allow_drafting: bool = True

    @model_validator(mode="after")
    def unique_keys(self):
        if len({field.key for field in self.fields}) != len(self.fields):
            raise ValueError("Field keys must be unique")
        return self


class Fill(BaseModel):
    key: str
    value: str | list[str] | None = None
    document_id: str | None = None
    source: Literal["profile", "project", "answer", "document", "drafted"]
    confidence: Literal["high", "medium", "low"] = "high"
    note: str = ""


class Unfilled(BaseModel):
    key: str
    reason: str


class Usage(BaseModel):
    drafted_fields: int
    remaining_today: int


class FillResponse(BaseModel):
    fills: list[Fill]
    unfilled: list[Unfilled]
    matched_opportunity_id: str | None
    usage: Usage
