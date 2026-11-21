"""Every tool the Assistant can use, by area."""

from . import catalog, kit, questions, records, scans, settings
from .base import Applied, Proposal, Tool

ALL: dict[str, Tool] = {
    tool.name: tool
    for module in (catalog, scans, records, kit, settings, questions)
    for tool in module.TOOLS
}

__all__ = ["ALL", "Applied", "Proposal", "Tool"]
