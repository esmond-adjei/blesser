"""Application note format: the template agents must follow.

Sections with nothing found are written as "Not found" rather than dropped, so
absence is explicit. The save_application handler refuses malformed notes.
"""

import re

NOTE_TEMPLATE = """\
## Summary
<2-4 sentences on what this application page says>

## Key dates
<deadlines found, or "Not found">

## Costs & waivers
<fees and waiver info, or "Not found">

## Watch-outs
<gotchas: tests, prerequisites, portals — or "None found">
"""

REQUIRED_SECTIONS = ("## Summary", "## Key dates", "## Costs & waivers", "## Watch-outs")


def _headings(notes: str) -> list[str]:
    return re.findall(r"^##\s+.+$", notes, flags=re.MULTILINE)


def verify_application_notes(tool_input: dict) -> str | None:
    """Error message with the template when notes don't follow NOTE_TEMPLATE, else None."""
    notes = (tool_input.get("notes") or "").strip()
    if not notes:
        return (
            "Notes are empty - write the application notes in the required "
            f"template format:\n{NOTE_TEMPLATE}"
        )
    present = [h.strip().lower() for h in _headings(notes)]
    missing = [s for s in REQUIRED_SECTIONS if s.lower() not in present]
    if missing:
        return (
            "Notes do not follow the application note template - missing "
            f"section(s): {', '.join(missing)}. Rewrite the notes exactly as:\n"
            f"{NOTE_TEMPLATE}"
        )
    return None
