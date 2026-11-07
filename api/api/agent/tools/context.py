"""Per-task dispatcher state: DB session, the run, and what this task has read and saved."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.scans.models import Scan


class ToolContext:
    def __init__(self, session: AsyncSession, run: Scan, user_id: str | None = None):
        self.session = session
        self.run = run
        self.user_id = user_id if user_id is not None else getattr(run, "user_id", None)
        # Dispatch refuses tools not shown to the model.
        self.offered_tools: set[str] | None = None
        self.opportunities_saved = 0
        # {url_key: text} of pages fetch_page returned; save_opportunity cites one.
        self.fetched_pages: dict[str, str] = {}
        # Reads that failed in this task, so the same call isn't resent.
        self.failed_calls: dict[str, str] = {}
