from datetime import datetime
from typing import Literal

from api.public.schemas import APIModel, PublicOpportunity


class MemberOpportunity(PublicOpportunity):
    audience: Literal["public", "members"]
    found_by: Literal["agent", "community", "staff"]
    created_at: datetime
    is_new: bool


class MemberPage(APIModel):
    items: list[MemberOpportunity]
    total: int
