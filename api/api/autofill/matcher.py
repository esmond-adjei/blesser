import calendar
import re
from dataclasses import dataclass
from datetime import date
from pathlib import PurePath

import phonenumbers
import pycountry

from api.autofill.normalization import normalize
from api.autofill.schemas import Fill, FormField
from api.autofill.vocabulary import AUTOCOMPLETE, DOCUMENT_KINDS, SENSITIVE, SYNONYMS

PROJECT_CONTEXT = {
    "startup",
    "company",
    "venture",
    "business",
    "project",
    "organisation",
    "organization",
}
BLOCKED_TYPES = {
    "password",
    "hidden",
    "submit",
    "reset",
    "button",
    "image",
    "color",
    "range",
}
BLOCKED_TEXT = re.compile(
    r"\b(password|credit card|debit card|card number|cardholder|cvv|cvc|iban|bank account|routing number|payment|social security|ssn|consent|agree to|terms and conditions|certify|declaration|signature)\b"
)
SENSITIVE_TEXT = re.compile(
    r"\b(passport|national id|national identity|national identification|ghana card|identity number|identification number)\b"
)
DATE_PATHS = {
    "date_of_birth",
    "founded_on",
    "passport_expiry",
    "education.start",
    "education.end",
    "experience.start",
    "experience.end",
}
COUNTRY_PATHS = {"nationality", "country_of_residence", "country", "education.country"}
GROUP_CONTEXT = {
    "education": ("education", "academic", "school", "university"),
    "experience": ("experience", "employment", "work history"),
    "languages": ("language", "languages"),
    "awards": ("award", "awards"),
    "publications": ("publication", "publications"),
    "references": ("reference", "referee", "references", "referees"),
    "team": ("team", "founder", "co founder"),
}


@dataclass(frozen=True)
class Match:
    source: str
    path: str
    value: object


def descriptor(field: FormField) -> str:
    return " ".join(
        normalize(value)
        for value in (
            field.label,
            field.name,
            field.id,
            field.placeholder,
            field.section,
        )
    )


def phrase(text: str, words: str) -> bool:
    return f" {normalize(words)} " in f" {text} "


def blocked(field: FormField) -> bool:
    return (
        field.type.lower() in BLOCKED_TYPES
        or bool(BLOCKED_TEXT.search(descriptor(field)))
        or any(token.startswith("cc-") for token in field.autocomplete.lower().split())
    )


def sensitive_field(field: FormField) -> str | None:
    for value in (field.label, field.name, field.id):
        text = normalize(value)
        text = re.sub(r"^(?:your|applicant|enter your|enter) ", "", text)
        for path, aliases in SENSITIVE.items():
            if text in {normalize(path), *aliases}:
                return path
    return None


def contains_sensitive(value: object, sensitive: dict) -> bool:
    text = str(value)
    compact = re.sub(r"\W", "", text).casefold()
    for secret in sensitive.values():
        if not secret:
            continue
        secret = str(secret)
        if secret.casefold() in text.casefold():
            return True
        normalized = re.sub(r"\W", "", secret).casefold()
        if len(normalized) >= 6 and normalized in compact:
            return True
    return False


def free_text(field: FormField) -> bool:
    if blocked(field) or SENSITIVE_TEXT.search(descriptor(field)) or field.options:
        return False
    if field.type.lower() not in {"text", "search", "", "textarea"}:
        return False
    return field.tag in {"textarea", "contenteditable"} or bool(
        re.search(
            r"\b(describe|explain|why|how|tell us|outline|discuss|summarize|summarise)\b",
            normalize(field.label),
        )
    )


def _nested_value(data: dict, path: str, field: FormField):
    if "." not in path:
        return data.get(path)
    group, key = path.split(".")
    items = data.get(group) or []
    if not items:
        return None
    index_match = re.search(r"\[(\d+)\]", field.name + field.id)
    number_match = re.search(
        r"\b(?:reference|referee|education|experience|team member|founder|award|publication|language) (\d+)\b",
        descriptor(field),
    )
    index = (
        int(index_match[1])
        if index_match
        else int(number_match[1]) - 1
        if number_match
        else 0
    )
    if len(items) > 1 and not index_match and not number_match:
        return None
    return items[index].get(key) if 0 <= index < len(items) else None


def _profile_value(profile, path, field):
    if path == "full_name":
        return " ".join(
            str(profile.get(k) or "").strip() for k in ("given_name", "family_name")
        ).strip()
    if (
        path in {"given_name", "family_name"}
        and not profile.get(path)
        and profile.get("full_name")
    ):
        pieces = profile["full_name"].strip().split()
        return pieces[0] if path == "given_name" else " ".join(pieces[1:])
    return _nested_value(profile, path, field)


def identify(
    field: FormField, profile: dict, project: dict, sensitive: dict
) -> Match | None:
    if blocked(field) or field.type.lower() == "file":
        return None
    secret_path = sensitive_field(field)
    if secret_path:
        return Match("profile", secret_path, sensitive.get(secret_path))
    if SENSITIVE_TEXT.search(descriptor(field)):
        return None
    parts = [
        re.sub(
            r"\b(reference|referee|education|experience|team member|founder|award|publication|language) \d+\b",
            r"\1",
            normalize(value),
        )
        for value in (field.label, field.name, field.id, field.placeholder)
    ]
    text = descriptor(field)
    project_context = bool(set(normalize(field.section).split()) & PROJECT_CONTEXT)
    candidates = []
    for source, paths in SYNONYMS["en"].items():
        for path, aliases in paths.items():
            if "." in path:
                group, key = path.split(".")
                if any(
                    phrase(normalize(field.section), hint)
                    for hint in GROUP_CONTEXT[group]
                ) and any(
                    part in {normalize(key), *(normalize(alias) for alias in aliases)}
                    for part in parts
                ):
                    candidates.append((100, source, path))
            for alias in (*aliases, path.replace(".", " ")):
                alias = normalize(alias)
                if (
                    source == "project"
                    and alias in {"name", "country", "city"}
                    and not project_context
                ):
                    continue
                matches = any(phrase(part, alias) for part in parts)
                if not matches and "." in path:
                    matches = phrase(text, alias)
                if not matches:
                    continue
                if alias in {
                    "name",
                    "country",
                    "city",
                    "address",
                    "gender",
                    "sex",
                    "email",
                    "phone",
                    "website",
                    "team",
                    "problem",
                    "solution",
                    "impact",
                    "experience",
                    "education",
                    "venture",
                } and not any(part == alias for part in parts):
                    continue
                score = len(alias.split()) * 10 + len(alias) / 100
                if project_context and source == "project":
                    score += 6
                if "." in path:
                    group = path.split(".")[0]
                    if phrase(normalize(field.section), group.rstrip("s")) or phrase(
                        normalize(field.section), group
                    ):
                        score += 15
                candidates.append((score, source, path))
    if project_context:
        for part in parts:
            generic = {
                "name": "name",
                "website": "website_url",
                "country": "country",
                "city": "city",
            }.get(part)
            if generic:
                candidates.append((30, "project", generic))
    for token in field.autocomplete.lower().split():
        if token in AUTOCOMPLETE:
            path = AUTOCOMPLETE[token]
            if not candidates or max(candidates)[0] < 20:
                candidates.append((25, "profile", path))
    if not candidates and field.type.lower() in {"email", "tel", "url"}:
        candidates.append(
            (
                1,
                "profile",
                {"email": "email", "tel": "phone", "url": "website_url"}[
                    field.type.lower()
                ],
            )
        )
    if project:
        for item in project.get("custom_fields", []):
            if normalize(item["label"]) in parts and normalize(item["label"]):
                return Match("project", "custom_fields", item["value"])
    if not candidates:
        return None
    _, source, path = max(candidates)
    data = profile if source == "profile" else project
    value = (
        _profile_value(data, path, field)
        if source == "profile"
        else _nested_value(data, path, field)
    )
    return Match(source, path, value)


def country(value: str):
    aliases = {
        "uk": "GB",
        "usa": "US",
        "u s a": "US",
        "united states of america": "US",
        "ghanaian": "GH",
        "nigerian": "NG",
        "british": "GB",
        "american": "US",
    }
    try:
        return pycountry.countries.lookup(aliases.get(normalize(value), value))
    except LookupError:
        return None


def _option_names(value: str, path: str) -> set[str]:
    names = {normalize(value)}
    if path in COUNTRY_PATHS:
        item = country(value)
        if item:
            names.update(
                normalize(getattr(item, key, ""))
                for key in (
                    "name",
                    "official_name",
                    "common_name",
                    "alpha_2",
                    "alpha_3",
                )
            )
    if normalize(value) in {"true", "yes", "1"}:
        names.update({"true", "yes", "1"})
    if normalize(value) in {"false", "no", "0"}:
        names.update({"false", "no", "0"})
    stage = {
        "early revenue": {"early revenue", "revenue generating", "early stage revenue"},
        "idea": {"idea", "ideation", "pre seed"},
        "prototype": {"prototype", "mvp", "minimum viable product"},
        "growth": {"growth", "scaling"},
    }
    if path == "stage":
        names.update(stage.get(normalize(value), set()))
    return names - {""}


def match_options(
    value: str | list[str], field: FormField, path: str = ""
) -> str | list[str] | None:
    values = value if isinstance(value, list) else [value]
    selected = []
    for item in values:
        names = _option_names(item, path)
        matches = [
            option
            for option in field.options
            if names & (_option_names(option.label, path) | {normalize(option.value)})
        ]
        if len(matches) != 1:
            return None
        selected.append(matches[0].value)
    return (
        list(dict.fromkeys(selected))
        if field.type.lower() == "checkbox"
        else selected[0]
        if len(selected) == 1
        else None
    )


def format_date(value: str, field: FormField) -> str | None:
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return None
    tokens = field.autocomplete.lower().split()
    text = normalize(f"{field.label} {field.name} {field.id}")
    if "bday-day" in tokens or re.search(
        r"\b(?:birth|dob) day\b|\bday of birth\b", text
    ):
        return str(parsed.day)
    if "bday-year" in tokens or re.search(
        r"\b(?:birth|dob) year\b|\byear of birth\b", text
    ):
        return str(parsed.year)
    if "bday-month" in tokens or re.search(
        r"\b(?:birth|dob) month\b|\bmonth of birth\b", text
    ):
        if field.options:
            for option in field.options:
                if normalize(option.label) in {
                    str(parsed.month),
                    f"{parsed.month:02}",
                    calendar.month_name[parsed.month].lower(),
                    calendar.month_abbr[parsed.month].lower(),
                }:
                    return option.value
        return str(parsed.month)
    if field.type.lower() == "date":
        return parsed.isoformat()
    if field.type.lower() == "month":
        return parsed.strftime("%Y-%m")
    hints = f"{field.placeholder} {field.help_text} {field.label}".lower()
    pattern = re.search(
        r"(?:yyyy|yy|dd|mm)[/.-](?:yyyy|yy|dd|mm)[/.-](?:yyyy|yy|dd|mm)", hints
    )
    if pattern:
        return parsed.strftime(
            pattern[0]
            .replace("yyyy", "%Y")
            .replace("yy", "%y")
            .replace("mm", "%m")
            .replace("dd", "%d")
        )
    return parsed.isoformat()


def format_phone(value: str, field: FormField, residence: str) -> str:
    item = country(residence)
    try:
        parsed = phonenumbers.parse(value, item.alpha_2 if item else None)
    except phonenumbers.NumberParseException:
        return value.strip()
    tokens = field.autocomplete.lower().split()
    hints = normalize(field.placeholder + " " + field.help_text)
    if "tel-country-code" in tokens:
        return f"+{parsed.country_code}"
    if "tel-area-code" in tokens:
        count = phonenumbers.length_of_national_destination_code(parsed)
        return str(parsed.national_number)[:count]
    if "tel-local" in tokens:
        count = phonenumbers.length_of_national_destination_code(parsed)
        return str(parsed.national_number)[count:]
    if "tel-national" in tokens or phrase(hints, "local format"):
        return phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.NATIONAL
        )
    formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    if phrase(hints, "digits only"):
        return formatted.lstrip("+")
    if phrase(hints, "international format"):
        return phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )
    return formatted


def render(value: object) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return "\n".join(render(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(
            f"{key.replace('_', ' ')}: {render(item)}"
            for key, item in value.items()
            if item not in (None, "", [])
        )
    return str(value) if value is not None else ""


def within_limits(value: str | list[str], field: FormField) -> bool:
    text = "\n".join(value) if isinstance(value, list) else value
    return (field.max_length is None or len(text) <= field.max_length) and (
        field.word_limit is None or len(text.split()) <= field.word_limit
    )


def deterministic(
    field: FormField, profile: dict, project: dict, sensitive: dict
) -> Fill | None:
    match = identify(field, profile, project, sensitive)
    if match is None or match.value is None or match.value == "" or match.value == []:
        return None
    value = render(match.value)
    if match.path in DATE_PATHS:
        value = format_date(value, field)
        if value is None:
            return None
    if match.path.endswith("phone"):
        value = format_phone(value, field, profile.get("country_of_residence", ""))
    if match.path in COUNTRY_PATHS and "country" in field.autocomplete.lower().split():
        item = country(value)
        value = item.alpha_2 if item else value
    if field.options and not (
        match.path in DATE_PATHS
        and any(option.value == value for option in field.options)
    ):
        choices = (
            [render(item) for item in match.value]
            if isinstance(match.value, list)
            and all(isinstance(item, str) for item in match.value)
            else value
        )
        value = match_options(choices, field, match.path)
        if value is None:
            return None
    elif field.type.lower() in {"checkbox", "radio"}:
        return None
    if not within_limits(value, field):
        return None
    if match.path not in SENSITIVE and contains_sensitive(value, sensitive):
        return None
    return Fill(
        key=field.key,
        value=value,
        source=match.source,
        note=f"From {match.source.replace('_', ' ')}: {match.path.replace('_', ' ')}",
    )


def accepts(document: dict, accept: str) -> bool:
    if not accept.strip():
        return True
    suffix = PurePath(document["filename"]).suffix.lower()
    mime = document["content_type"].lower()
    return any(
        token == suffix
        or token == mime
        or token == "*/*"
        or (token.endswith("/*") and mime.startswith(token[:-1]))
        for token in (item.strip().lower() for item in accept.split(","))
    )


def document_match(field: FormField, documents: list[dict]) -> Fill | None:
    if field.type.lower() != "file" or blocked(field):
        return None
    text = descriptor(field)
    kinds = [
        (len(alias), kind)
        for kind, aliases in DOCUMENT_KINDS.items()
        for alias in aliases
        if phrase(text, alias)
    ]
    if not kinds:
        return None
    kind = max(kinds)[1]
    matches = [
        doc
        for doc in documents
        if doc["kind"] == kind and doc["is_default"] and accepts(doc, field.accept)
    ]
    if len(matches) != 1:
        return None
    return Fill(
        key=field.key,
        source="document",
        document_id=matches[0]["id"],
        note=f"Default {kind.replace('_', ' ')}",
    )
