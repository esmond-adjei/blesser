from datetime import datetime

from pydantic import BaseModel


class DraftOut(BaseModel):
    id: str
    candidate_id: str
    professor_name: str
    # Recipient details for the email card; null when unknown.
    professor_email: str | None = None
    professor_photo_url: str | None = None
    school_name: str | None = None
    program_name: str | None = None
    candidate_status: str
    similarity_score: float | None
    rationale: str | None
    subject: str
    body: str
    created_at: datetime


class DraftUpdate(BaseModel):
    subject: str | None = None
    body: str | None = None


class BulkDraftRequest(BaseModel):
    candidate_ids: list[str]


class ReviewItem(BaseModel):
    candidate_id: str
    approved: bool


class BulkReviewRequest(BaseModel):
    reviews: list[ReviewItem]
