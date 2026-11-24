from datetime import datetime
from typing import Literal

from pydantic import Field

from api.public.schemas import APIModel, PublicOpportunity


class MemberOpportunity(PublicOpportunity):
    audience: Literal["public", "members"]
    found_by: Literal["agent", "community", "staff"]
    created_at: datetime
    is_new: bool
    # A listing the member's own scan found that others can't see until it's reviewed.
    in_review: bool = False
    # Only on sort=for_you: the score and the member's fields this listing mentions.
    match_score: float | None = None
    match_terms: list[str] = Field(default_factory=list)


class MemberPage(APIModel):
    items: list[MemberOpportunity]
    total: int
