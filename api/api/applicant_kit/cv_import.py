"""Suggests Applicant Kit profile fields from a CV the member stored in Documents.

The CV's text is read in a resource-capped child process (cv_text), then the
configured model returns the fields it finds through a strict schema. Every
value goes through the profile validators and anything invalid is dropped, so
the member only ever reviews values the profile could save. Nothing is saved
here: the member applies what they want from the review.

Privacy: the CV text and the model's answer are never logged or stored. Failures
log the error type only. The private details (national ID, passport) have no
place in the schema, so they are never asked for or returned.
"""

import asyncio
import json
import logging
import re
import sys
import weakref
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from api.agent.llm.factory import get_provider
from api.agent.orchestrator import _chat_with_retry
from api.agent.untrusted import UNTRUSTED_CONTENT_RULE
from api.applicant_kit import cv_text, schemas
from api.core.exceptions import DomainError, UnprocessableError

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30
_slots: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)


class CvReadUnavailable(DomainError):
    status_code = 503


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Link(_Strict):
    label: str
    url: str


class _Education(_Strict):
    institution: str
    qualification: str
    field: str
    grade: str
    start: str
    end: str
    country: str


class _Experience(_Strict):
    organization: str
    role: str
    current: bool
    start: str
    end: str
    location: str
    summary: str


class _Language(_Strict):
    language: str
    level: Literal["basic", "conversational", "fluent", "native", ""]


class _Award(_Strict):
    title: str
    issuer: str
    year: str


class _Publication(_Strict):
    title: str
    venue: str
    year: str
    url: str


class _Reference(_Strict):
    name: str
    title: str
    organization: str
    email: str
    phone: str
    relationship: str


class CvFields(_Strict):
    given_name: str
    family_name: str
    preferred_name: str
    pronouns: str
    date_of_birth: str
    gender: str
    nationality: str
    country_of_birth: str
    place_of_birth: str
    country_of_residence: str
    city: str
    address_line1: str
    address_line2: str
    postal_code: str
    email: str
    phone: str
    linkedin_url: str
    website_url: str
    github_url: str
    other_links: list[_Link]
    headline: str
    short_bio: str
    long_bio: str
    education: list[_Education]
    experience: list[_Experience]
    skills: list[str]
    languages: list[_Language]
    awards: list[_Award]
    publications: list[_Publication]
    references: list[_Reference]


SCALARS = [
    name for name, field in CvFields.model_fields.items() if field.annotation is str
]

RULES = (
    "You read a CV and return the applicant's profile by calling cv_profile exactly once. "
    "Only use facts written in the CV. Use an empty string or an empty list for anything "
    "the CV does not state; never guess. Never return national ID, passport, tax, bank or "
    "social security numbers anywhere, even if the CV shows them. "
    "Dates: YYYY-MM-DD for date_of_birth; YYYY-MM for education and experience start and "
    "end (YYYY when only the year is given); empty when unknown. Set current=true and "
    "end empty for a role the CV marks as present or current. Years are four digits. "
    "Names: given_name holds first and middle names, family_name the surname. "
    "Countries and nationality in English, for example Ghana and Ghanaian. "
    "headline: the CV's own title line or current role, under 140 characters. "
    "long_bio: the CV's profile or summary section as written. short_bio: under 300 "
    "characters, a third person summary using only that section. Keep education and "
    "experience most recent first. Experience summaries keep the CV's wording. "
    "Language level: native, fluent, conversational or basic, empty if not stated. "
    "Links in the CV's link list belong in linkedin_url, github_url, website_url or "
    "other_links as fits. "
) + UNTRUSTED_CONTENT_RULE


def _schema() -> dict:
    schema = CvFields.model_json_schema()

    def strict(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                strict(value)
        elif isinstance(node, list):
            for value in node:
                strict(value)

    strict(schema)
    return schema


def _semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _slots:
        _slots[loop] = asyncio.Semaphore(2)
    return _slots[loop]


async def read_text(path: Path, content_type: str) -> dict:
    """The CV's text and links. Raises UnprocessableError when there is none."""
    if content_type not in cv_text.TYPES:
        raise UnprocessableError(
            "Blesser can read CVs saved as PDF or Word (.docx). Upload one of those."
        )
    async with _semaphore():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "api.applicant_kit.cv_text",
            str(path),
            content_type,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={"PYTHONPATH": ":".join(sys.path), "LC_ALL": "C.UTF-8"},
        )
        try:
            out, _ = await asyncio.wait_for(process.communicate(), TIMEOUT_SECONDS)
        except TimeoutError:
            process.kill()
            await process.wait()
            result = {"error": cv_text.UNREADABLE}
        else:
            try:
                result = json.loads(out) if process.returncode == 0 else None
            except ValueError:
                result = None
            if not isinstance(result, dict):
                result = {"error": cv_text.UNREADABLE}
    error = result.get("error")
    if error == cv_text.NO_TEXT:
        raise UnprocessableError(
            "This CV has no text Blesser can read, which usually means it is a scan "
            "or a photo. Upload the Word file or a PDF exported from it."
        )
    if error == cv_text.ENCRYPTED:
        raise UnprocessableError(
            "This PDF is password protected. Upload a copy without a password."
        )
    if error or not isinstance(result.get("text"), str):
        raise UnprocessableError(
            "Blesser couldn't read this file. Try a PDF exported from Word or Google Docs."
        )
    return {"text": result["text"], "links": result.get("links") or []}


async def ask_model(cv: dict) -> CvFields:
    payload = json.dumps(
        {
            "today": datetime.now(UTC).date().isoformat(),
            "links": cv["links"],
            "cv": cv["text"],
        },
        ensure_ascii=False,
    )
    try:
        response = await _chat_with_retry(
            get_provider(),
            [
                {
                    "role": "user",
                    "content": f'<untrusted_content source="cv">\n'
                    f"{payload.replace('</untrusted_content>', '</untrusted-content>')}\n"
                    "</untrusted_content>",
                }
            ],
            RULES,
            [
                {
                    "name": "cv_profile",
                    "description": "Return the profile fields found in the CV.",
                    "parameters": _schema(),
                    "strict": True,
                }
            ],
            0,
        )
        if response.truncated:
            raise ValueError("truncated")
        if response.tool_calls:
            if (
                len(response.tool_calls) != 1
                or response.tool_calls[0].name != "cv_profile"
            ):
                raise ValueError("expected one cv_profile call")
            return CvFields.model_validate(response.tool_calls[0].arguments)
        return CvFields.model_validate_json(response.text)
    except Exception as exc:  # noqa: BLE001 - the member can retry or fill by hand
        # Error type only: the CV and the model's answer are personal data.
        log.warning("CV reading failed (%s)", type(exc).__name__)
        raise CvReadUnavailable(
            "Blesser couldn't read your CV just now. Try again in a few minutes."
        ) from None


def _valid(model: type[BaseModel], data: dict) -> dict | None:
    try:
        return model.model_validate(data).model_dump(mode="json")
    except ValidationError:
        return None


def _month(value: str) -> str | None:
    value = value.strip()
    if m := re.fullmatch(r"(\d{4})-(\d{2})(?:-\d{2})?", value):
        year, month = int(m[1]), int(m[2])
        return f"{year:04d}-{month:02d}-01" if 1 <= month <= 12 else None
    if re.fullmatch(r"\d{4}", value):
        return f"{value}-01-01"
    return None


def _year(value: str) -> int | None:
    value = value.strip()
    return int(value) if re.fullmatch(r"\d{4}", value) else None


def _url(value: str) -> str:
    value = value.strip()
    if (
        value
        and not re.match(r"^[a-z][a-z0-9+.-]*:", value, re.IGNORECASE)
        and "." in value
    ):
        value = "https://" + value.lstrip("/")
    return value


def _short_bio(value: str) -> str:
    value = " ".join(value.split())
    limit = schemas.ProfileIn.model_fields["short_bio"].metadata[0].max_length
    if len(value) <= limit:
        return value
    cut = value[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > 0 else ""


def _dated(model, item: dict, *, current: bool = False) -> dict | None:
    data = {**item, "start": _month(item["start"]), "end": _month(item["end"])}
    if current:
        data["end"] = None
    found = _valid(model, data)
    if found is None and data["start"] and data["end"]:
        # Swapped or unclear dates: keep the entry, drop the dates.
        found = _valid(model, {**data, "start": None, "end": None})
    return found


def to_profile(fields: CvFields) -> dict:
    """Only the fields found, each one valid for the profile."""
    raw = fields.model_dump()
    found: dict = {}
    for name in SCALARS:
        value = raw[name].strip()
        if name in {"linkedin_url", "website_url", "github_url"}:
            value = _url(value)
        elif name == "short_bio":
            value = _short_bio(value)
        elif name == "date_of_birth":
            value = value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else ""
        if not value:
            continue
        checked = _valid(schemas.ProfileIn, {name: value})
        if checked is not None and checked[name]:
            found[name] = checked[name]

    def collect(name, items, convert):
        limit = next(
            m.max_length
            for m in schemas.ProfileIn.model_fields[name].metadata
            if hasattr(m, "max_length")
        )
        kept = []
        for item in items:
            value = convert(item)
            if (
                value
                and value not in kept
                and any(v for k, v in value.items() if k not in {"level", "current"})
            ):
                kept.append(value)
        if kept:
            found[name] = kept[:limit]

    collect(
        "other_links",
        raw["other_links"],
        lambda i: _valid(schemas.Link, {**i, "url": _url(i["url"])}),
    )
    collect(
        "education",
        raw["education"],
        lambda i: _dated(schemas.Education, i),
    )
    collect(
        "experience",
        raw["experience"],
        lambda i: _dated(schemas.Experience, i, current=i["current"]),
    )
    collect(
        "languages",
        raw["languages"],
        lambda i: (
            _valid(
                schemas.Language,
                {"language": i["language"], "level": i["level"] or "fluent"},
            )
            if i["language"].strip()
            else None
        ),
    )
    collect(
        "awards",
        raw["awards"],
        lambda i: _valid(schemas.Award, {**i, "year": _year(i["year"])}),
    )
    collect(
        "publications",
        raw["publications"],
        lambda i: _valid(
            schemas.Publication, {**i, "year": _year(i["year"]), "url": _url(i["url"])}
        ),
    )
    collect(
        "references",
        raw["references"],
        lambda i: (
            _valid(schemas.Reference, i)
            or _valid(schemas.Reference, {**i, "email": ""})
        ),
    )
    skills = []
    for skill in raw["skills"]:
        skill = " ".join(skill.split())
        if (
            skill
            and len(skill) <= 200
            and skill.casefold() not in {s.casefold() for s in skills}
        ):
            skills.append(skill)
    if skills:
        found["skills"] = skills[:100]
    return found
