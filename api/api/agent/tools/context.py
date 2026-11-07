"""Per-task dispatcher state: DB session, active run/program, save counters."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.prospects.models import Program
    from api.runs.models import Run


class ToolContext:
    """Per-task state the dispatcher needs."""

    def __init__(
        self,
        session: AsyncSession,
        run: Run,
        program: Program | None = None,
        user_id: str | None = None,
        metered: bool = True,
    ):
        self.session = session
        # Research agent saves spend the run's caps; user-approved chat saves don't.
        self.metered = metered
        self.run = run
        self.program = program
        # None only for test doubles; registry/config reads then use defaults.
        self.user_id = user_id if user_id is not None else getattr(run, "user_id", None)
        self.last_candidate_id: str | None = None
        # Anti-runaway counters against config max_*_per_task.
        self.programs_saved = 0
        self.professors_saved = 0
        self.drafts_saved = 0
        self.applications_saved = 0
        # Dispatch refuses tools not shown to the model.
        self.offered_tools: set[str] | None = None
        # The student's own addition: its own allowance, never cut by the run's cap.
        self.user_added = False
        self.discovery_shard: str | None = None
        # A parked task waits out OpenAlex outages instead of saving unverified.
        self.park_on_openalex_budget = False
        self.openalex_wait = None
        self.failed_openalex_calls: dict[str, str] = {}
        self.tool_call_counts: dict[str, int] = {}
        self.failed_calls: dict[str, str] = {}
        self.author_candidates: dict[str, dict] = {}
        self.works_by_author: dict[str, list[dict]] = {}
        self.alignment_scores: list[dict] = []
        # Works from the account's professor index, not a lookup in this task.
        self.indexed_authors: set[str] = set()


def cached_interest_vector(ctx: ToolContext) -> list[float] | None:
    raw = getattr(ctx.run, "interest_embedding", None)
    if not raw:
        return None
    try:
        vec = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return vec if isinstance(vec, list) and vec else None
