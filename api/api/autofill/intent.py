import re
from dataclasses import dataclass

from api.autofill.normalization import intent_label, normalize
from api.autofill.schemas import FormField
from api.autofill.vocabulary import SYNONYMS

QUALIFIERS = {
    "references": r"\b(?:referees?|references?)\b",
    "team": r"\b(?:team(?: member)?|co founder|founder)\b",
    "education": r"\b(?:institutions?|universit(?:y|ies)|schools?|colleges?|education|academic)\b",
    "experience": r"\b(?:employers?|employment|work experience|work history|experience)\b",
    "birth": r"\b(?:birth|born)\b",
    "residence": r"\b(?:residence|residential|residing|live)\b",
    "citizenship": r"\b(?:citizenship|citizen)\b",
    "project": r"\b(?:startup|company|venture|business|project|organization|organisation|headquarters)\b",
    "languages": r"\b(?:languages?)\b",
    "awards": r"\b(?:awards?)\b",
    "publications": r"\b(?:publications?|paper)\b",
}
HEADS = {
    "country": r"\bcountr(?:y|ies)\b",
    "place": r"\b(?:place|city|town)\b",
    "date": r"\b(?:date|day|month|year)\b",
    "email": r"\b(?:e mail|email)(?: address)?\b",
    "phone": r"\b(?:phone|telephone|mobile|contact number)\b",
    "website": r"\b(?:website|web site|url)\b",
    "name": r"\b(?:name|institution|employer|organization|organisation)\b",
    "qualification": r"\b(?:qualification|degree|education level)\b",
    "field": r"\b(?:field of study|major|discipline|subject)\b",
    "start": r"\b(?:start|enrollment|enrolment|admission)\b",
    "end": r"\b(?:end|graduation|completion)\b",
    "grade": r"\b(?:grade|gpa)\b",
    "role": r"\b(?:role|position|job title|title)\b",
    "gender": r"\b(?:gender|sex)\b",
    "bio": r"\b(?:bio|biography)\b",
    "relationship": r"\brelationship\b",
    "summary": r"\b(?:summary|responsibilities|description)\b",
    "location": r"\blocation\b",
    "level": r"\b(?:level|proficiency)\b",
}
ATTRIBUTES = {
    "education": {
        "name": "institution",
        "qualification": "qualification",
        "field": "field",
        "start": "start",
        "end": "end",
        "grade": "grade",
        "country": "country",
    },
    "experience": {
        "name": "organization",
        "role": "role",
        "start": "start",
        "end": "end",
        "location": "location",
        "summary": "summary",
    },
    "references": {
        "name": "name",
        "role": "title",
        "email": "email",
        "phone": "phone",
        "relationship": "relationship",
    },
    "team": {
        "name": "name",
        "role": "role",
        "email": "email",
        "gender": "gender",
        "bio": "bio",
    },
    "project": {
        "name": "name",
        "country": "country",
        "place": "city",
        "website": "website_url",
        "role": "name",
    },
    "birth": {
        "country": "country_of_birth",
        "place": "place_of_birth",
        "date": "date_of_birth",
    },
    "residence": {"country": "country_of_residence", "place": "city"},
    "citizenship": {"country": "citizenship"},
    "languages": {"level": "level", "name": "language"},
    "awards": {"name": "title", "role": "title", "date": "year"},
    "publications": {
        "name": "title",
        "role": "title",
        "date": "year",
        "website": "url",
    },
}
PROFILE_QUALIFIERS = {"birth", "residence", "citizenship"}


@dataclass(frozen=True)
class Intent:
    source: str
    path: str
    qualified: bool = True


def qualifier(text):
    return next(
        (group for group, pattern in QUALIFIERS.items() if re.search(pattern, text)),
        None,
    )


def resolve(group, head):
    attribute = ATTRIBUTES[group].get(head, head)
    source = "project" if group in {"project", "team"} else "profile"
    path = (
        attribute
        if group == "project" or group in PROFILE_QUALIFIERS
        else f"{group}.{attribute}"
    )
    return Intent(source, path)


def parse_intent(field: FormField) -> Intent | None:
    label = normalize(intent_label(field.label))
    section = normalize(field.section)
    if re.search(r"\bcurrent (?:employment|employer|work|experience)\b", section):
        if label in {"role", "job title", "position", "title"}:
            return Intent("profile", "current_role")
        if label in {"employer", "company", "organization", "organisation", "name"}:
            return Intent("profile", "current_employer")
    if label in {"country code", "area code", "phone number"} and "phone" in section:
        return Intent("profile", "phone")
    if (
        label in {"date", "day", "month", "year"}
        and "date" in section
        and not qualifier(section)
    ):
        return Intent("profile", "form_date")
    for value in (
        intent_label(field.label),
        field.name,
        field.id,
        intent_label(field.placeholder),
    ):
        text = normalize(value)
        if re.search(r"\bcurrent (?:company|employer)\b", text):
            return Intent("profile", "current_employer")
        if re.search(r"\bcurrent (?:role|job title|position)\b", text):
            return Intent("profile", "current_role")
        if re.search(
            r"\bhighest (?:qualification|degree|education|level of education)\b", text
        ):
            return Intent("profile", "highest_qualification")
        if re.search(r"\bage(?: in years)?\b", text) and not re.search(
            r"\b(?:range|group|minimum|maximum|under|over)\b", text
        ):
            return Intent("profile", "age")
        if text in {"full address", "complete address", "full mailing address"}:
            return Intent("profile", "full_address")
        if text in {"birthplace", "birth place"}:
            return Intent("profile", "place_of_birth")
        if text in {"citizenship", "country of citizenship"}:
            return Intent("profile", "citizenship")
        group = qualifier(text)
        if group:
            remainder = re.sub(QUALIFIERS[group], " ", text)
            if group != "education" and re.search(r"\binstitution\b", remainder):
                return Intent(
                    "project" if group in {"project", "team"} else "profile",
                    f"{group}.institution",
                )
            heads = [
                head for head, pattern in HEADS.items() if re.search(pattern, remainder)
            ]
            if "date" in heads and any(head in heads for head in ("start", "end")):
                heads.remove("date")
            if heads:
                head = heads[0]
                if (
                    group in {"references", "experience"}
                    and re.search(
                        r"\b(?:organization|organisation|company)\b", remainder
                    )
                    and head == "name"
                ):
                    return Intent("profile", f"{group}.organization")
                return resolve(group, head)
    section_group = qualifier(normalize(field.section))
    if section_group:
        for value in (
            intent_label(field.label),
            field.name,
            field.id,
            intent_label(field.placeholder),
        ):
            text = normalize(value)
            if text in {
                "first name",
                "given name",
                "last name",
                "family name",
                "surname",
                "full name",
            }:
                head = (
                    "name"
                    if text == "full name"
                    else "given_name"
                    if text in {"first name", "given name"}
                    else "family_name"
                )
                return resolve(section_group, head)
            if text in {
                "organization",
                "organisation",
                "company",
                "organization name",
                "organisation name",
            } and section_group in {"references", "experience"}:
                return Intent("profile", f"{section_group}.organization")
            for head, pattern in HEADS.items():
                if re.fullmatch(pattern, text):
                    return resolve(section_group, head)
    for path, aliases in SYNONYMS["en"]["profile"].items():
        if label and label in {normalize(alias) for alias in (*aliases, path)}:
            return Intent("profile", path, False)
    return None
