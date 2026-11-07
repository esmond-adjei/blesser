from pydantic import BaseModel, Field

from api.runs.schemas import (
    MAX_PER_PROGRAM_LIMIT,
    MAX_PROFESSORS_LIMIT,
    MAX_PROGRAMS_LIMIT,
)


class ProgramSeed(BaseModel):
    """One preselected program: skip discovery, go straight to research."""

    school_name: str
    school_country: str | None = None
    program_name: str
    department_url: str | None = None


class CreateRunFromListRequest(BaseModel):
    # Comma-separated degree keys ("phd, masters"); older runs may say "either".
    degree_level: str
    interest_statement: str
    interest_document_id: str | None = None
    programs: list[ProgramSeed] = Field(max_length=MAX_PROGRAMS_LIMIT)
    max_programs: int | None = Field(default=None, ge=1, le=MAX_PROGRAMS_LIMIT)
    max_professors: int | None = Field(default=None, ge=1, le=MAX_PROFESSORS_LIMIT)
    max_professors_per_program: int | None = Field(
        default=None, ge=1, le=MAX_PER_PROGRAM_LIMIT
    )
    flow_id: str | None = None
    # "system", a provider, or None/"default".
    llm_provider: str | None = Field(default=None, max_length=32)


class ProgramOut(BaseModel):
    id: str
    name: str
    department_url: str | None = None
    professors: int


class SchoolOut(BaseModel):
    id: str
    name: str
    country: str | None = None
    website_url: str | None = None
    image_url: str | None = None
    tier: str | None = None
    # Oldest first; filled by the account listing only.
    run_ids: list[str] = []
    programs: list[ProgramOut]


class ProgramCreate(BaseModel):
    name: str
    department_url: str | None = None


class SchoolCreate(BaseModel):
    name: str
    country: str | None = None
    website_url: str | None = None
    programs: list[ProgramCreate] = Field(default_factory=list)


class SchoolUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    website_url: str | None = None


class ProgramUpdate(BaseModel):
    name: str | None = None
    department_url: str | None = None


class ProfessorOut(BaseModel):
    id: str
    name: str
    openalex_id: str | None = None
    profile_url: str | None = None
    lab_name: str | None = None
    photo_url: str | None = None
    papers: int


class ProgramDetailOut(BaseModel):
    id: str
    name: str
    department_url: str | None = None
    school_id: str
    school_name: str
    professors: list[ProfessorOut]


class SocialLink(BaseModel):
    label: str
    url: str


class ProfessorUpdate(BaseModel):
    name: str | None = None
    profile_url: str | None = None
    email: str | None = None
    lab_name: str | None = None
    bio: str | None = None
    bio_source: str | None = None
    photo_url: str | None = None
    socials: list[SocialLink] | None = None


class ProfessorCreate(BaseModel):
    name: str
    profile_url: str | None = None
    email: str | None = None
    openalex_id: str | None = None


class Coauthor(BaseModel):
    name: str
    openalex_id: str | None = None


class PaperOut(BaseModel):
    #: None for papers an index entry holds without a saved row.
    id: str | None = None
    title: str
    abstract: str | None = None
    year: int | None = None
    url: str | None = None
    citations: int | None = None
    publication_type: str | None = None
    coauthors: list[Coauthor] = []


class ProfessorMatchIn(BaseModel):
    """Interests from a run, or from an interest document."""

    run_id: str | None = None
    document_id: str | None = None
    save: bool = False


class MatchedPaper(BaseModel):
    title: str
    year: int | None = None
    abstract: str | None = None
    url: str | None = None
    score: float


class FitRating(BaseModel):
    # 0-4, between levels when Jev is split; label is the nearest level.
    level: float
    label: str
    score: float
    confidence: float


class ProfessorMatchOut(BaseModel):
    score: float
    # strong / moderate / weak / unrelated (scoring.score_band).
    band: str
    paper: str | None
    candidate_id: str | None
    # The run a save lands in; None when no run uses the document.
    run_id: str | None = None
    top_papers: list[MatchedPaper] = []
    interest: str = ""
    papers_scored: int = 0
    # Jev's judgment of the fit (verification.rate_fit); None when off.
    fit: FitRating | None = None


class ProfessorDetailOut(BaseModel):
    id: str
    name: str
    profile_url: str | None = None
    email: str | None = None
    openalex_id: str | None = None
    lab_name: str | None = None
    bio: str | None = None
    bio_source: str | None = None
    photo_url: str | None = None
    socials: list[SocialLink] = []
    program_id: str
    program_name: str
    school_name: str
    candidate_id: str | None = None
    papers: list[PaperOut]
