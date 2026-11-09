from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    TypeAdapter,
    model_validator,
)


def http_url(value: str) -> str:
    if value:
        TypeAdapter(HttpUrl).validate_python(value)
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Use an absolute HTTP(S) URL without credentials")
        if any(char.isspace() for char in value):
            raise ValueError("URLs cannot contain whitespace")
    return value


def email(value: str) -> str:
    if value:
        return str(TypeAdapter(EmailStr).validate_python(value))
    return value


def single_line(value: str) -> str:
    if any(ord(char) < 32 for char in value):
        raise ValueError("Use a single line without control characters")
    return value


Short = Annotated[str, Field(max_length=200), AfterValidator(single_line)]
Line = Annotated[str, Field(max_length=500), AfterValidator(single_line)]
Text = Annotated[str, Field(max_length=20000)]
URL = Annotated[str, Field(max_length=2048), AfterValidator(http_url)]
Email = Annotated[str, Field(max_length=254), AfterValidator(email)]
ID = Annotated[str, Field(min_length=1, max_length=100)]
Year = Annotated[int, Field(ge=1900, le=2200)]
Kind = Literal[
    "cv",
    "cover_letter",
    "pitch_deck",
    "transcript",
    "certificate",
    "budget",
    "financials",
    "id_document",
    "photo",
    "logo",
    "other",
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def ignore_readonly(cls, data):
        if isinstance(data, dict):
            readonly = {
                "id",
                "completeness",
                "created_at",
                "updated_at",
                "word_count",
            } - cls.model_fields.keys()
            return {k: v for k, v in data.items() if k not in readonly}
        return data


class Link(Input):
    label: Short = ""
    url: URL = ""


class DateRange(Input):
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.start and self.end and self.end < self.start:
            raise ValueError("End date must be on or after start date")
        return self


class Education(DateRange):
    institution: Short = ""
    qualification: Short = ""
    field: Short = ""
    grade: Short = ""
    country: Short = ""


class Experience(DateRange):
    organization: Short = ""
    role: Short = ""
    current: bool = False
    location: Short = ""
    summary: Text = ""

    @model_validator(mode="after")
    def current_has_no_end(self):
        if self.current and self.end:
            raise ValueError("Current experience cannot have an end date")
        return self


class Language(Input):
    language: Short = ""
    level: Literal["basic", "conversational", "fluent", "native"] = "basic"


class Award(Input):
    title: Short = ""
    issuer: Short = ""
    year: Year | None = None


class Publication(Input):
    title: Line = ""
    venue: Short = ""
    year: Year | None = None
    url: URL = ""


class Reference(Input):
    name: Short = ""
    title: Short = ""
    organization: Short = ""
    email: Email = ""
    phone: Short = ""
    relationship: Short = ""


class Sensitive(Input):
    national_id: Annotated[
        str, Field(max_length=100, pattern=r"^[^*]*$"), AfterValidator(single_line)
    ] = ""
    passport_number: Annotated[
        str, Field(max_length=100, pattern=r"^[^*]*$"), AfterValidator(single_line)
    ] = ""
    passport_expiry: date | None = None


class ProfileIn(Input):
    given_name: Short = ""
    family_name: Short = ""
    preferred_name: Short = ""
    pronouns: Short = ""
    date_of_birth: date | None = None
    gender: Short = ""
    nationality: Short = ""
    country_of_residence: Short = ""
    city: Short = ""
    address_line1: Line = ""
    address_line2: Line = ""
    postal_code: Short = ""
    email: Email = ""
    phone: Short = ""
    linkedin_url: URL = ""
    website_url: URL = ""
    github_url: URL = ""
    other_links: list[Link] = Field(default_factory=list, max_length=30)
    headline: Line = ""
    short_bio: Annotated[str, Field(max_length=300)] = ""
    long_bio: Text = ""
    education: list[Education] = Field(default_factory=list, max_length=50)
    experience: list[Experience] = Field(default_factory=list, max_length=50)
    skills: list[Short] = Field(default_factory=list, max_length=100)
    languages: list[Language] = Field(default_factory=list, max_length=50)
    awards: list[Award] = Field(default_factory=list, max_length=100)
    publications: list[Publication] = Field(default_factory=list, max_length=100)
    references: list[Reference] = Field(default_factory=list, max_length=30)
    sensitive: Sensitive = Field(default_factory=Sensitive)

    @model_validator(mode="after")
    def birth_in_past(self):
        if self.date_of_birth and self.date_of_birth > datetime.now(UTC).date():
            raise ValueError("Date of birth cannot be in the future")
        return self


class ProfileOut(ProfileIn):
    sensitive: dict[str, str | None]
    completeness: int
    updated_at: datetime


class TeamMember(Input):
    name: Short = ""
    role: Short = ""
    bio: Text = ""
    email: Email = ""
    linkedin_url: URL = ""
    is_founder: bool = False
    gender: Short = ""


class CustomField(Input):
    label: Short = ""
    value: Text = ""


def money(value: str) -> str:
    if value:
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Use a nonnegative decimal amount") from exc
        if not amount.is_finite() or amount < 0:
            raise ValueError("Use a nonnegative decimal amount")
    return value


Money = Annotated[str, Field(max_length=50), AfterValidator(money)]


class ProjectIn(Input):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    tagline: Line = ""
    website_url: URL = ""
    logo_document_id: ID | None = None
    stage: Literal["idea", "prototype", "early_revenue", "growth", "other"] = "idea"
    sector: Short = ""
    country: Short = ""
    city: Short = ""
    founded_on: date | None = None
    legal_status: Short = ""
    registration_number: Short = ""
    problem: Text = ""
    solution: Text = ""
    target_customers: Text = ""
    market_size: Text = ""
    business_model: Text = ""
    competition: Text = ""
    traction: Text = ""
    impact: Text = ""
    why_now: Text = ""
    team: list[TeamMember] = Field(default_factory=list, max_length=100)
    team_size: Annotated[int, Field(ge=1, le=10000000)] | None = None
    women_led: bool = False
    youth_led: bool = False
    revenue_last_12_months: Money = ""
    funding_raised: Money = ""
    amount_sought: Money = ""
    currency: Annotated[str, Field(pattern=r"^([A-Z]{3})?$", max_length=3)] = ""
    use_of_funds: Text = ""
    document_ids: list[ID] = Field(default_factory=list, max_length=100)
    custom_fields: list[CustomField] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def founding_in_past(self):
        if self.founded_on and self.founded_on > datetime.now(UTC).date():
            raise ValueError("Founded date cannot be in the future")
        return self


class ProjectOut(ProjectIn):
    id: str
    completeness: int
    created_at: datetime
    updated_at: datetime


class DocumentPatch(Input):
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    kind: Kind | None = None
    project_ids: list[ID] | None = Field(default=None, max_length=100)
    is_default: bool | None = None

    @model_validator(mode="after")
    def no_explicit_nulls(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Document fields cannot be null")
        return self


class DocumentOut(BaseModel):
    id: str
    kind: Kind
    title: str
    filename: str
    content_type: str
    size_bytes: int
    project_ids: list[str]
    is_default: bool
    created_at: datetime


class AnswerIn(Input):
    question: Annotated[str, Field(min_length=1, max_length=2000)]
    answer: Annotated[str, Field(min_length=1, max_length=50000)]
    tags: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=30
    )
    project_id: ID | None = None


class AnswerOut(AnswerIn):
    id: str
    word_count: int
    updated_at: datetime
