"""Per-task dispatcher state: DB session, the run, and what this task has read and saved."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.scans.models import Scan, ScanTask


class ToolContext:
    def __init__(self, session: AsyncSession, run: Scan, user_id: str | None = None):
        self.session = session
        self.run = run
        self.user_id = user_id if user_id is not None else getattr(run, "user_id", None)
        # Dispatch refuses tools not shown to the model.
        self.offered_tools: set[str] | None = None
        self.opportunities_saved = 0
        self.reverify_id: str | None = None
        # {url_key: text} of pages fetch_page returned; save_opportunity cites one.
        self.fetched_pages: dict[str, str] = {}
        # Reads that failed in this task, so the same call isn't resent.
        self.failed_calls: dict[str, str] = {}
        self.page_notes: dict[str, str] = {}
        self.known_pages: dict[str, str] = {}
        self.fetch_windows: set[tuple[str, int]] = set()
        self.fetch_locks: dict = {}
        self.saved_titles: list[str] = []
        self.category: str = "startup"
        self.extraction_confidence: float = 1.0
        self.scan_task: ScanTask | None = None
