from datetime import datetime

from pydantic import BaseModel

from api.prospects.schemas import PaperOut


class CandidateOut(BaseModel):
    id: str
    run_id: str
    professor_id: str
    program_id: str
    school_id: str
    professor_name: str
    school_name: str
    program_name: str
    # Pictures for rows and cards; null when none was found.
    professor_photo_url: str | None = None
    school_image_url: str | None = None
    similarity_score: float | None
    rationale: str | None
    status: str
    draft_id: str | None = None
    draft_subject: str | None = None
    draft_body: str | None = None
    draft_created_at: datetime | None = None
    draft_count: int = 0


class ApproveDraftRequest(BaseModel):
    approved: bool


class ReviewItem(BaseModel):
    candidate_id: str
    approved: bool


class BulkReviewRequest(BaseModel):
    reviews: list[ReviewItem]


class ProfessorMatchRef(BaseModel):
    id: str
    run_id: str
    similarity_score: float | None
    status: str
    interest: str | None = None


class CandidateDetailOut(BaseModel):
    """Full review record: identity, graph position, evidence, and draft."""

    id: str
    run_id: str
    interest: str | None = None
    professor_id: str
    program_id: str
    school_id: str
    professor_name: str
    school_name: str
    program_name: str
    professor_photo_url: str | None = None
    school_image_url: str | None = None
    similarity_score: float | None
    rationale: str | None
    status: str
    papers: list[PaperOut]
    draft_id: str | None = None
    draft_subject: str | None = None
    draft_body: str | None = None
    draft_created_at: datetime | None = None
    draft_task_id: str | None = None
    draft_task_status: str | None = None
    # Every match for this professor, this one included, best first.
    matches: list[ProfessorMatchRef] = []
