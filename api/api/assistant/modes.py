"""Gradis modes: named bundles of allowed tools plus a prompt addendum.

A mode only narrows: per-tool settings still decide what is enabled, and
write tools still ask first. A read is anything outside WRITE_TOOLS that
is not a suggestion.
"""

from dataclasses import dataclass

from api.assistant import tools as assistant_tools

#: Tools that propose a change for the student to apply, and change
#: nothing on their own.
SUGGEST_TOOLS = frozenset({"cv_suggest_changes", "suggest_changes"})


@dataclass(frozen=True)
class Mode:
    label: str
    #: Tool names this mode may offer; None means every enabled tool.
    allowed: frozenset[str] | None
    prompt: str

    def allows(self, tool_name: str) -> bool:
        return self.allowed is None or tool_name in self.allowed

    def narrow(self, definitions: list[dict]) -> list[dict]:
        """The definitions this mode keeps, in their order."""
        if self.allowed is None:
            return definitions
        return [d for d in definitions if d.get("name") in self.allowed]


def _reads() -> frozenset[str]:
    return frozenset(
        name
        for name in assistant_tools.HANDLERS
        if name not in assistant_tools.WRITE_TOOLS and name not in SUGGEST_TOOLS
    )


READ_TOOLS = _reads()

DEFAULT_MODE = "agent"

MODES: dict[str, Mode] = {
    "chat": Mode(
        label="Chat",
        allowed=READ_TOOLS,
        prompt=(
            "\n\n## Mode: Chat\nTalk things through and look up information from "
            "the student's records and the web when helpful. Prefer looking "
            "things up over guessing, and cite what you found. You cannot "
            "change records or store document suggestions in this mode. If the "
            "student asks for a change, say Agent mode can make it."
        ),
    ),
    "agent": Mode(label="Agent", allowed=None, prompt=""),
}


def get_mode(name: str | None) -> Mode:
    return MODES.get(name or DEFAULT_MODE, MODES[DEFAULT_MODE])
