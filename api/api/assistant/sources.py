import re
from datetime import date

from api.app.schemas import MemberOpportunity
from api.assistant.schemas import Source

_REFERENCE = re.compile(r"\[(s\d+)\]")
_DEADLINE_REFERENCE = re.compile(r"\[deadline:(s\d+)\]")
_UNGROUNDED_TIME = re.compile(
    r"\b(?:\d{1,4}[-/]\d{1,2}(?:[-/]\d{1,4})?|\d{1,2}:\d{2}|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may(?=\s+\d)|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow|"
    r"midnight|noon|eod|end of (?:the |this )?(?:day|week|month|year)|"
    r"(?:next|this|\d+|a|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:day|week|month|year)s?|rolling|"
    r"apply any ?time)\b",
    re.IGNORECASE,
)
_DATE_CLAIM = re.compile(
    r"\b(?:(?:closes?|closing|due|deadline|ends?)\s+"
    r"(?:on|in|by|is|at|until|before|after)|"
    r"(?:open|accepted|submit|apply)\s+(?:by|until|before))\b",
    re.IGNORECASE,
)


class SourceRegistry:
    def __init__(self):
        self.sources: dict[str, Source] = {}
        self.keys: dict[tuple[str, str], str] = {}
        self.deadlines: dict[str, str] = {}

    def register(self, kind, row, *, detail="", title=None, url=None):
        record = (kind, row["id"])
        key = self.keys.get(record, f"s{len(self.sources) + 1}")
        opportunity = (
            MemberOpportunity.model_validate(row) if kind == "opportunity" else None
        )
        self.keys[record] = key
        self.sources[key] = Source(
            key=key,
            kind=kind,
            id=row["id"],
            title=title or row["title"],
            detail=detail,
            url=url,
            opportunity=opportunity,
        )
        deadline = row.get("deadline_date")
        if row.get("rolling"):
            self.deadlines[key] = "Rolling, apply any time"
        elif isinstance(deadline, (date, str)):
            day = date.fromisoformat(str(deadline))
            self.deadlines[key] = f"{day.day} {day:%b %Y}"
        return key

    def render(self, text):
        text = re.sub(r"\brejected\b", "Not this time", text, flags=re.IGNORECASE)
        text = re.sub(r"[ \t]*[—·][ \t]*", ", ", text)
        used = {}
        cited_deadlines = False

        def cite(match):
            key = match[1]
            if key in self.sources:
                used[key] = self.sources[key]
            return ""

        def cite_deadline(match):
            nonlocal cited_deadlines
            cite(match)
            if match[1] in self.deadlines:
                cited_deadlines = True
                return self.deadlines[match[1]]
            return "No deadline confirmed"

        parts = []
        for paragraph in text.strip().splitlines():
            prose = _DEADLINE_REFERENCE.sub("", paragraph)
            has_deadline = _DEADLINE_REFERENCE.search(paragraph)
            if _UNGROUNDED_TIME.search(prose) or (
                not has_deadline and _DATE_CLAIM.search(prose)
            ):
                for match in _REFERENCE.finditer(paragraph):
                    cite(match)
                for match in _DEADLINE_REFERENCE.finditer(paragraph):
                    cite(match)
                continue
            paragraph = _DEADLINE_REFERENCE.sub(cite_deadline, paragraph)
            clean = _REFERENCE.sub(cite, paragraph).rstrip()
            parts.append(re.sub(r"[ \t]+([.,!?])", r"\1", clean))
        reply = "\n".join(parts).strip()
        return (
            reply,
            [source.model_dump(mode="json") for source in used.values()],
            cited_deadlines,
        )
