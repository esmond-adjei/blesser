"""CV schemas. The API shapes are mirrored manually by webapp/src/lib/types.ts."""

from typing import Literal

from pydantic import BaseModel, Field


class UnitSource(BaseModel):
    format: Literal["docx"] = "docx"
    part: str  # e.g. "word/document.xml", "word/header1.xml"
    path: str  # stable path to the paragraph/cell/textbox within the part
    fingerprint: str  # hash of normalized text + structural position


class UnitStyle(BaseModel):
    font_family: str | None = None
    font_size_pt: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    color: str | None = None
    alignment: str | None = None


class UnitGeometry(BaseModel):
    """Not populated yet: always None."""

    page: int
    x: float
    y: float
    width: float
    height: float


class LengthBudget(BaseModel):
    max_chars: int | None = None
    basis: str = "render_unavailable"


class EditableUnit(BaseModel):
    id: str
    type: Literal["heading", "paragraph", "bullet", "table_cell", "textbox", "link", "image"]
    text: str | None = None
    source: UnitSource
    style: UnitStyle | None = None
    geometry: UnitGeometry | None = None
    block_id: str | None = None
    section_hint: str | None = None
    section_confidence: float | None = None
    length_budget: LengthBudget | None = None
    editable: bool = True
    read_only_reason: str | None = None
    # Image units only: basename of the embedded media file (e.g.
    # "image1.png") plus its media type. The Markdown CV leaves images out.
    image_ref: str | None = None
    image_media_type: str | None = None
    # Heading units only: 1 for a Title style, n + 1 for Heading n.
    heading_level: int | None = None


class IrDocument(BaseModel):
    version_id: str | None = None
    units: list[EditableUnit] = []
    unextracted: list[str] = []
    fidelity_class: Literal["high", "medium", "low"] = "high"


MAX_MARKDOWN_CHARS = 60_000

#: api/cv/models.py DOCUMENT_KINDS, as a type.
DocumentKind = Literal["cv", "sop", "diversity_statement", "research_proposal", "interest", "note"]


class FolderOut(BaseModel):
    id: str
    name: str
    sort_order: int
    document_count: int = 0
    created_at: object | None = None
    updated_at: object | None = None

    model_config = {"arbitrary_types_allowed": True}


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class FolderOrder(BaseModel):
    """Every folder id, in the order to show them."""

    ids: list[str] = Field(max_length=500)


class VersionSummary(BaseModel):
    id: str
    document_id: str
    name: str
    candidate_id: str | None = None
    professor_id: str | None = None
    application_id: str | None = None
    target_label: str | None = None
    revision: int
    forked_from_revision: int | None = None
    base_updated: bool = False
    # Its own limits; None uses the base's (base_word_limit on VersionOut).
    word_limit: int | None = None
    page_limit: int | None = None
    created_at: object | None = None
    updated_at: object | None = None

    model_config = {"arbitrary_types_allowed": True}


class VersionOut(VersionSummary):
    markdown: str
    # Linked professor, resolved when the row still exists.
    professor_name: str | None = None
    school_name: str | None = None
    base_word_limit: int | None = None
    base_page_limit: int | None = None


class DocumentSummary(BaseModel):
    id: str
    title: str
    kind: DocumentKind = "cv"
    folder_id: str | None = None
    word_limit: int | None = None
    page_limit: int | None = None
    format: str
    size_bytes: int
    has_original: bool
    revision: int
    version_count: int = 0
    created_at: object | None = None
    updated_at: object | None = None
    # Its tailored versions, most recently edited first (the CV list
    # shows them under their base CV).
    versions: list[VersionSummary] = []

    model_config = {"arbitrary_types_allowed": True}


class DocumentOut(DocumentSummary):
    markdown: str


class DocumentCreate(BaseModel):
    """A base document written or pasted in, with no file."""

    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(default="", max_length=MAX_MARKDOWN_CHARS)
    kind: DocumentKind = "cv"
    folder_id: str | None = None


WordLimit = Field(default=None, ge=1, le=100_000)
PageLimit = Field(default=None, ge=1, le=100)


class DocumentMeta(BaseModel):
    """What a document is filed under, and its limits; never its text.
    Only the fields sent change (folder_id null moves it to the top level;
    a limit null removes it)."""

    folder_id: str | None = None
    word_limit: int | None = WordLimit
    page_limit: int | None = PageLimit


class VersionMeta(BaseModel):
    """A tailored version's own limits, for a program's rules. Only the
    fields sent change; null falls back to the base's."""

    word_limit: int | None = WordLimit
    page_limit: int | None = PageLimit


class CheckFinding(BaseModel):
    kind: Literal["placeholder", "date_mismatch", "name_mismatch", "unknown_faculty"]
    message: str
    # Exact text on that line, to mark in the editor.
    quote: str
    line: int


class ChecksOut(BaseModel):
    findings: list[CheckFinding]


class TextUpdate(BaseModel):
    """Save from the editor. base_revision is the revision the text was
    edited from; a newer stored revision answers 409."""

    base_revision: int
    markdown: str | None = Field(default=None, max_length=MAX_MARKDOWN_CHARS)
    title: str | None = Field(default=None, min_length=1, max_length=200)


class VersionCreate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    candidate_id: str | None = None
    application_id: str | None = None
    # Start a fresh copy even if one already exists for this candidate.
    new: bool = False
    # The text to start from: an unsaved variant edited in the browser
    # before the student chose to save it. Default: the base CV's text.
    markdown: str | None = Field(default=None, max_length=MAX_MARKDOWN_CHARS)


class LayoutIn(BaseModel):
    markdown: str = Field(default="", max_length=MAX_MARKDOWN_CHARS)


class PageBreak(BaseModel):
    page: int
    # 1-based source line that opens the page.
    line: int


class LayoutOut(BaseModel):
    pages: int
    breaks: list[PageBreak]


class SuggestionIn(BaseModel):
    find: str = Field(min_length=1, max_length=8000)
    replace: str = Field(max_length=8000)
    rationale: str | None = Field(default=None, max_length=2000)


class SuggestionsCreate(BaseModel):
    version_id: str | None = None
    suggestions: list[SuggestionIn] = Field(min_length=1, max_length=20)


class TextRange(BaseModel):
    """A span of the saved text in UTF-16 code units, the way the editor
    (and any browser) counts positions."""

    start: int = Field(ge=0, alias="from")
    end: int = Field(ge=0, alias="to")

    model_config = {"populate_by_name": True}


#: Quick actions on a selection; "custom" carries the student's own words.
SuggestAction = Literal["improve", "shorten", "quantify", "tailor", "custom"]


class ModelPick(BaseModel):
    """The model picker's choice: a configured provider id, or "system" for
    the shared model. Omitted means the account's default."""

    provider: str = Field(min_length=1, max_length=64)


class SelectionSuggest(BaseModel):
    """Ask for a suggested rewrite of one selected passage. The text is
    the saved text at `base_revision`; `text` must be what `range` covers
    in it, so a request made against older text is refused."""

    version_id: str | None = None
    base_revision: int
    range: TextRange
    text: str = Field(min_length=1, max_length=8000)
    action: SuggestAction = "improve"
    instruction: str | None = Field(default=None, max_length=1000)
    model: ModelPick | None = None


class SuggestionRefresh(BaseModel):
    """Ask again for a stale suggestion, against the text as it is now."""

    model: ModelPick | None = None


class BaseChange(BaseModel):
    """One change to the base since a version was forked: `before` became
    `after`. `applicable` when `before` occurs exactly once in the version,
    so it can be suggested there."""

    before: str
    after: str
    applicable: bool


class BaseChanges(BaseModel):
    base_updated: bool
    forked_from_revision: int | None = None
    base_revision: int
    changes: list[BaseChange]


class SyncOut(BaseModel):
    suggestions: list["SuggestionOut"]
    # Changes that touch text the version has since changed itself.
    skipped: int


class SuggestionAccept(BaseModel):
    # The student's edit of the suggested text, when they changed it.
    replace: str | None = Field(default=None, max_length=8000)
    # Required when the change adds words the base CV never mentions.
    confirm_new_terms: bool = False


class SuggestionOut(BaseModel):
    id: str
    document_id: str
    version_id: str | None
    find: str
    replace: str
    rationale: str | None = None
    claim_check: dict = {}
    limit_check: dict | None = None
    status: str
    # Whether `find` still occurs exactly once in the current text.
    applicable: bool = True
    superseded_by: str | None = None
    created_by: str
    created_at: object | None = None
    resolved_at: object | None = None

    model_config = {"arbitrary_types_allowed": True}


SyncOut.model_rebuild()
