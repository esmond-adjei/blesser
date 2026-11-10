import calendar
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import PurePath

import phonenumbers

from api.autofill import concepts
from api.autofill.intent import parse_intent
from api.autofill.normalization import intent_label, normalize
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
COUNTRY_PATHS = concepts.COUNTRY_PATHS
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
    rule: str = ""
    confidence: str = "high"


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


def sensitive_descriptor(field: FormField) -> str:
    return descriptor(field.model_copy(update={"label": intent_label(field.label)}))


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


def infer(profile, path):
    if path in {"country_of_birth", "citizenship"}:
        item = concepts.country(profile.get("nationality", ""))
        return (item["name"], "nationality") if item else (None, "")
    if path == "nationality":
        item = concepts.country(profile.get("country_of_birth", ""))
        return (item["demonyms"][0], "country_of_birth") if item else (None, "")
    if path == "age":
        try:
            birth = date.fromisoformat(profile.get("date_of_birth", ""))
        except (ValueError, TypeError):
            return None, ""
        today = datetime.now(UTC).date()
        if birth > today:
            return None, ""
        return today.year - birth.year - (
            (today.month, today.day) < (birth.month, birth.day)
        ), "date_of_birth"
    if path in {"current_role", "current_employer"}:
        rows = [row for row in profile.get("experience", []) if row.get("current")]
        key = "role" if path == "current_role" else "organization"
        values = {row[key] for row in rows if row.get(key)}
        return (
            (next(iter(values)), "experience.current")
            if len(values) == 1
            else (None, "")
        )
    if path == "highest_qualification":
        rows = [
            row["qualification"]
            for row in profile.get("education", [])
            if row.get("qualification")
        ]
        ranks = [
            (concepts.DEGREE_RANK.get(concepts.canonical(value, "degree")), value)
            for value in rows
        ]
        if ranks and all(rank is not None for rank, _ in ranks):
            return max(ranks)[1], "education"
    if path == "full_address":
        parts = [
            profile.get(key)
            for key in (
                "address_line1",
                "address_line2",
                "city",
                "postal_code",
                "country_of_residence",
            )
        ]
        if profile.get("address_line1"):
            return ", ".join(filter(None, parts)), "address_parts"
    return None, ""


def resolve_match(source, path, field, profile, project, rule):
    data = profile if source == "profile" else project
    value = (
        _profile_value(data, path, field)
        if source == "profile"
        else _nested_value(data, path, field)
    )
    if source == "profile" and value in (None, "", []):
        value, inferred_from = infer(profile, path)
        if inferred_from:
            return Match(source, path, value, f"inferred:{inferred_from}", "medium")
    return Match(source, path, value, rule)


def identify(
    field: FormField, profile: dict, project: dict, sensitive: dict
) -> Match | None:
    if blocked(field) or field.type.lower() == "file":
        return None
    secret_path = sensitive_field(field)
    if secret_path:
        return Match(
            "profile", secret_path, sensitive.get(secret_path), f"exact:{secret_path}"
        )
    if SENSITIVE_TEXT.search(sensitive_descriptor(field)):
        return None
    label = normalize(intent_label(field.label))
    if re.search(
        r"\b(?:years? of experience|interested in|preference|preferred position|desired|expected|earliest available)\b",
        label,
    ):
        return None
    intent = parse_intent(field)
    if intent:
        prefix = "qualifier" if intent.qualified else "matched"
        return resolve_match(
            intent.source,
            intent.path,
            field,
            profile,
            project,
            f"{prefix}:{intent.path}",
        )
    parts = [
        re.sub(
            r"\b(reference|referee|education|experience|team member|founder|award|publication|language) \d+\b",
            r"\1",
            normalize(value),
        )
        for value in (
            intent_label(field.label),
            field.name,
            field.id,
            intent_label(field.placeholder),
        )
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
                return Match(
                    "project", "custom_fields", item["value"], "matched:custom_fields"
                )
    if not candidates:
        return None
    _, source, path = max(candidates)
    return resolve_match(source, path, field, profile, project, f"matched:{path}")


def country(value: str):
    return concepts.country(value)


def option_match(value: str | list[str], field: FormField, path: str = ""):
    values = value if isinstance(value, list) else [value]
    selected = []
    rules = []
    kind = concepts.concept_kind(path, field.label)
    for item in values:
        target = concepts.canonical(item, kind)
        matches = []
        rule = ""
        if target:
            for option in field.options:
                concept = concepts.canonical(option.label, kind) or concepts.canonical(
                    option.value, kind
                )
                if concept == target:
                    matches.append(option)
            rule = f"concept:{kind}"
        if not matches:
            matches = [
                option
                for option in field.options
                if normalize(item) in {normalize(option.label), normalize(option.value)}
                and (
                    not target
                    or concepts.canonical(option.label, kind) in {None, target}
                )
            ]
            rule = "option:normalized"
        if not matches and not target:
            tokens = set(normalize(item).split())
            scored = []
            for option in field.options:
                other = set(normalize(option.label).split())
                union = tokens | other
                score = len(tokens & other) / len(union) if union else 0
                if score >= 0.8 and len(tokens & other) >= 2:
                    scored.append((score, option))
            if scored:
                best = max(score for score, _ in scored)
                matches = [option for score, option in scored if score == best]
            rule = "option:tokens"
        if len(matches) != 1:
            return None, ""
        selected.append(matches[0].value)
        rules.append(rule)
    if not selected:
        return None, ""
    result = (
        list(dict.fromkeys(selected))
        if field.type.lower() == "checkbox"
        else selected[0]
        if len(selected) == 1
        else None
    )
    return result, rules[0] if len(set(rules)) == 1 else "option:mixed"


def match_options(
    value: str | list[str], field: FormField, path: str = ""
) -> str | list[str] | None:
    return option_match(value, field, path)[0]


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
    token = r"(?:yyyy|yy|mm|m|dd|d)"
    pattern = re.search(rf"\b{token}([/.-]){token}\1{token}\b", hints)
    if pattern:
        parts = {
            "yyyy": f"{parsed.year}",
            "yy": f"{parsed.year % 100:02}",
            "mm": f"{parsed.month:02}",
            "m": f"{parsed.month}",
            "dd": f"{parsed.day:02}",
            "d": f"{parsed.day}",
        }
        return pattern[1].join(parts[p] for p in pattern[0].split(pattern[1]))
    return parsed.isoformat()


def format_phone(value: str, field: FormField, residence: str) -> str:
    item = country(residence)
    try:
        parsed = phonenumbers.parse(value, item["alpha_2"] if item else None)
    except phonenumbers.NumberParseException:
        return value.strip()
    tokens = field.autocomplete.lower().split()
    hints = normalize(field.placeholder + " " + field.help_text)
    label = normalize(field.label)
    if "tel-country-code" in tokens or label == "country code":
        return f"+{parsed.country_code}"
    if "tel-area-code" in tokens or label == "area code":
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
    rule = match.rule
    if match.path in DATE_PATHS:
        value = format_date(value, field)
        if value is None:
            return None
    if match.path.endswith("phone"):
        value = format_phone(value, field, profile.get("country_of_residence", ""))
    if match.path in COUNTRY_PATHS and match.path != "nationality":
        item = country(value)
        if item:
            code_format = (
                "country" in field.autocomplete.lower().split() or field.max_length == 2
            )
            value = item["alpha_2"] if code_format else item["name"]
    choice_values = None
    if field.options and not (
        match.path in DATE_PATHS
        and any(option.value == value for option in field.options)
    ):
        choices = (
            [item["language"] for item in match.value if item.get("language")]
            if match.path == "languages" and isinstance(match.value, list)
            else [render(item) for item in match.value]
            if isinstance(match.value, list)
            and all(isinstance(item, str) for item in match.value)
            else value
        )
        choice_values = choices
        value, option_rule = option_match(choices, field, match.path)
        if value is None:
            return None
        if not rule.startswith(("qualifier:", "inferred:")):
            rule = option_rule
    elif field.type.lower() in {"checkbox", "radio"}:
        return None
    if not within_limits(value, field):
        return None
    if match.path not in SENSITIVE and contains_sensitive(value, sensitive):
        return None
    note = f"From {match.source.replace('_', ' ')}: {match.path.replace('_', ' ')}"
    if rule.startswith("concept:"):
        selected = value if isinstance(value, list) else [value]
        labels = [option.label for option in field.options if option.value in selected]
        original = (
            ", ".join(choice_values)
            if isinstance(choice_values, list)
            else choice_values
        )
        candidate = f"Matched '{original}' to '{', '.join(labels)}'"
        if not contains_sensitive(candidate, sensitive):
            note = candidate
    elif rule.startswith("inferred:"):
        origin = rule.removeprefix("inferred:")
        description = {"experience.current": "current experience"}.get(
            origin, origin.replace("_", " ")
        )
        original = profile.get(origin, match.value)
        candidate = f"From your {description} '{render(original)}'"
        note = (
            f"From your {description}"
            if contains_sensitive(candidate, sensitive)
            else candidate
        )
    return Fill(
        key=field.key,
        value=value,
        source=match.source,
        rule=rule,
        confidence=match.confidence,
        note=note,
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
        rule=f"document:{kind}",
        document_id=matches[0]["id"],
        note=f"Default {kind.replace('_', ' ')}",
    )
