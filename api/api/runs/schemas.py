from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SchoolTier = Literal["top", "strong", "solid", "accessible"]

# Hard ceilings whatever the plan: each dial multiplies paid agent tasks. Plans clamp further.
MAX_PROGRAMS_LIMIT = 50
MAX_PROFESSORS_LIMIT = 300
MAX_PER_PROGRAM_LIMIT = 30


class CreateRunRequest(BaseModel):
    region: str
    field: str
    # Comma-separated degree keys ("phd, masters"); older runs may say "either".
    degree_level: str
    interest_statement: str
    interest_document_id: str | None = None
    max_programs: int | None = Field(default=None, ge=1, le=MAX_PROGRAMS_LIMIT)
    max_professors: int | None = Field(default=None, ge=1, le=MAX_PROFESSORS_LIMIT)
    max_professors_per_program: int | None = Field(
        default=None, ge=1, le=MAX_PER_PROGRAM_LIMIT
    )
    # None = the built-in Standard flow.
    flow_id: str | None = None
    # Empty = no preference; several tiers split the programme cap evenly.
    school_tiers: list[SchoolTier] = Field(default_factory=list, max_length=4)
    # "system" = Auto, else a configured provider; None or "default" = the account default at creation.
    llm_provider: str | None = Field(default=None, max_length=32)


class RunOut(BaseModel):
    id: str
    region: str
    field: str
    degree_level: str
    status: str
    interest_statement: str
    created_at: datetime
    # None while live; set on the run detail, not the list.
    finished_at: datetime | None = None
    elapsed_seconds: float | None = None
    updated_at: datetime | None = None
    max_programs: int | None = None
    max_professors: int | None = None
    max_professors_per_program: int | None = None
    tasks: dict[str, int]
    candidates: int
    flow_id: str | None = None
    school_tiers: list[str] = Field(default_factory=list)
    llm_provider: str | None = None
    agent_states: dict[str, str] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class TaskOut(BaseModel):
    """One unit of agent work plus its trace; `log` streams in while it runs."""

    id: str
    task_type: str
    target_id: str | None = None
    target_name: str | None = None
    status: str
    error: str | None = None
    turns: int | None = None
    final_text: str | None = None
    log: list[dict] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    updated_at: datetime | None = None


class BoardTaskOut(BaseModel):
    """A board card: TaskOut without the trace."""

    id: str
    task_type: str
    target_name: str | None = None
    status: str
    turns: int | None = None
    error: str | None = None
    updated_at: datetime | None = None


class BoardOut(BaseModel):
    """Kanban columns keyed by status."""

    pending: list[BoardTaskOut] = []
    running: list[BoardTaskOut] = []
    done: list[BoardTaskOut] = []
    error: list[BoardTaskOut] = []
    paused: list[BoardTaskOut] = []
    cancelled: list[BoardTaskOut] = []
    deferred: list[BoardTaskOut] = []


class RunListOut(BaseModel):
    """One run plus live progress counts."""

    id: str
    region: str
    field: str
    degree_level: str
    status: str
    interest_statement: str
    created_at: datetime
    finished_at: datetime | None = None
    elapsed_seconds: float | None = None
    max_programs: int | None = None
    max_professors: int | None = None
    max_professors_per_program: int | None = None
    tasks: dict[str, int]
    candidates: int
    llm_provider: str | None = None


class RunUpdate(BaseModel):
    interest_statement: str | None = None
    max_programs: int | None = Field(default=None, ge=1, le=MAX_PROGRAMS_LIMIT)
    max_professors: int | None = Field(default=None, ge=1, le=MAX_PROFESSORS_LIMIT)
    max_professors_per_program: int | None = Field(
        default=None, ge=1, le=MAX_PER_PROGRAM_LIMIT
    )
    # null or "default" = the account default.
    llm_provider: str | None = Field(default=None, max_length=32)


class ToolCallOut(BaseModel):
    """One tool-call record with parsed payloads."""

    turn: int
    tool_name: str
    input: dict | None = None
    result: dict | list | str | None = None
    ok: bool | None = None


class WorkerOut(BaseModel):
    worker_id: str
    concurrency: int
    started_at: datetime | None = None
    last_seen_at: datetime | None = None
    lag_seconds: float | None = None
    alive: bool


class ToolStatOut(BaseModel):
    calls: int
    errors: int


class ModelUsageOut(BaseModel):
    provider: str | None = None
    model: str | None = None
    tasks: int
    input_tokens: int
    output_tokens: int


class UsageOut(BaseModel):
    """Cost accounting for a run."""

    input_tokens: int
    output_tokens: int
    turns: int
    tasks: dict[str, int]
    tools: dict[str, ToolStatOut]
    cache_read_tokens: int = 0
    model_seconds: float = 0.0
    tool_seconds: float = 0.0
    models: list[ModelUsageOut] = []
    candidates: int = 0
    tokens_per_candidate: int | None = None
    first_candidate_seconds: float | None = None
    active_seconds: float = 0.0
    # Counts by ResearchTask.path / path_reason.
    narrow_paths: dict[str, int] = {}
    narrow_fallbacks: dict[str, int] = {}
    narrow_skips: dict[str, int] = {}


class RunEstimateOut(BaseModel):
    """Projected tokens for a run; allowance is null when the account uses its own key."""

    estimated_tokens: int
    narrow_tasks: int
    basis: str  # "history" | "defaults"
    daily_allowance_left: int | None = None
    fits: bool | None = None


class GateCountOut(BaseModel):
    gate: str
    label: str
    count: int


class RefusalsOut(BaseModel):
    """Why researched professors weren't saved; recovered refusals still count."""

    researched: int
    saved: int
    not_saved: list[GateCountOut]
    refusals: list[GateCountOut]
    lexical_scores: int = 0


class RunFacultyOut(BaseModel):
    """Slim faculty row."""

    id: str
    name: str
    program_id: str
    program: str
    school_id: str
    school: str
    lab_name: str | None
    photo_url: str | None
    papers: int
    candidate_id: str | None
    # Set by the school faculty view.
    candidate_status: str | None = None
    similarity_score: float | None = None
    candidate_run_id: str | None = None
    # Set by the professors catalog.
    bio: str | None = None
    school_image_url: str | None = None


class InterestSuggestion(BaseModel):
    """One proposed interest and where in the CV it came from."""

    text: str
    document_id: str
    document_title: str
    section: str
    evidence: str


class InterestSource(BaseModel):
    document_id: str
    title: str


class InterestSuggestionsIn(BaseModel):
    # None = the newest few CVs.
    document_id: str | None = None


class InterestSuggestionsOut(BaseModel):
    sources: list[InterestSource] = []
    suggestions: list[InterestSuggestion] = []
    # "model" | "heuristic" | "none"
    method: str


class BudgetMeter(BaseModel):
    used: int
    limit: int


class RunBudgetOut(BaseModel):
    """Research allowance per cap. Read-only lookups never count."""

    programs: BudgetMeter
    professors: BudgetMeter
    user_programs: BudgetMeter
