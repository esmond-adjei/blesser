import calendar
import json
import re
from collections import defaultdict
from functools import cache
from pathlib import Path

import pycountry

from api.autofill.normalization import normalize

COUNTRY_PATHS = {
    "nationality",
    "citizenship",
    "country_of_birth",
    "country_of_residence",
    "country",
    "education.country",
}
ALIASES = {
    "gender": {
        "male": ("male", "man", "m", "masculine"),
        "female": ("female", "woman", "f", "feminine"),
        "nonbinary": ("non binary", "nonbinary", "genderqueer", "gender diverse"),
        "undisclosed": (
            "prefer not to say",
            "prefer not to disclose",
            "decline to self identify",
            "do not wish to answer",
        ),
    },
    "degree": {
        "secondary": (
            "secondary",
            "high school",
            "secondary school",
            "wassce",
            "sssce",
        ),
        "certificate": ("certificate", "vocational certificate"),
        "diploma": (
            "diploma",
            "hnd",
            "higher national diploma",
            "associate",
            "associate degree",
        ),
        "bachelor": (
            "bsc",
            "b sc",
            "bs",
            "b s",
            "ba",
            "b a",
            "beng",
            "b eng",
            "btech",
            "bachelor",
            "bachelors",
            "bachelor s",
            "bachelor s degree",
            "bachelors degree",
            "bachelor of science",
            "bachelor of arts",
            "undergraduate",
            "undergraduate degree",
        ),
        "master": (
            "msc",
            "m sc",
            "ms",
            "m s",
            "ma",
            "m a",
            "mphil",
            "m phil",
            "mba",
            "meng",
            "master",
            "masters",
            "master s",
            "master s degree",
            "masters degree",
            "master of science",
            "master of philosophy",
            "master of arts",
        ),
        "doctorate": (
            "phd",
            "ph d",
            "dphil",
            "d phil",
            "doctorate",
            "doctoral",
            "doctoral degree",
            "doctor of philosophy",
        ),
    },
    "boolean": {
        "yes": (
            "true",
            "yes",
            "y",
            "1",
            "agree",
            "i agree",
            "i consent",
            "i accept",
            "accept",
            "consent",
            "agreed",
            "yes i agree",
            "yes i consent",
        ),
        "no": (
            "false",
            "no",
            "n",
            "0",
            "disagree",
            "i disagree",
            "i do not agree",
            "i do not consent",
            "i decline",
            "decline",
            "do not accept",
            "no i do not consent",
        ),
    },
    "employment": {
        "fulltime": ("full time", "fulltime", "ft", "full time employment"),
        "parttime": ("part time", "parttime", "pt", "part time employment"),
        "contract": ("contract", "contractor", "contractual", "independent contractor"),
        "temporary": ("temporary", "temp", "fixed term"),
        "internship": ("intern", "internship", "industrial attachment"),
        "selfemployed": ("self employed", "self employment", "freelance", "freelancer"),
        "volunteer": ("volunteer", "voluntary", "volunteering"),
    },
    "proficiency": {
        "basic": (
            "basic",
            "beginner",
            "elementary",
            "a1",
            "a2",
            "limited working proficiency",
            "elementary proficiency",
        ),
        "conversational": (
            "conversational",
            "intermediate",
            "b1",
            "b2",
            "working proficiency",
            "professional working proficiency",
        ),
        "fluent": (
            "fluent",
            "advanced",
            "proficient",
            "c1",
            "c2",
            "full professional proficiency",
        ),
        "native": (
            "native",
            "native speaker",
            "mother tongue",
            "native or bilingual",
            "native bilingual",
            "native or bilingual proficiency",
        ),
    },
    "title": {
        "mr": ("mr", "mister"),
        "ms": ("ms", "miz"),
        "mrs": ("mrs", "missus"),
        "miss": ("miss",),
        "mx": ("mx",),
        "dr": ("dr", "doctor"),
        "prof": ("prof", "professor"),
    },
    "stage": {
        "idea": ("idea", "ideation", "pre seed"),
        "prototype": ("prototype", "mvp", "minimum viable product"),
        "revenue": ("early revenue", "revenue generating", "early stage revenue"),
        "growth": ("growth", "scaling"),
    },
}
DEGREE_RANK = {key: index for index, key in enumerate(ALIASES["degree"])}


@cache
def countries():
    return json.loads((Path(__file__).with_name("data") / "countries.json").read_text())


@cache
def country_index():
    index = defaultdict(set)
    for row in countries():
        for name in (
            row["alpha_2"],
            row["alpha_3"],
            row["numeric"],
            *row["names"],
            *row["demonyms"],
        ):
            if name:
                index[normalize(name)].add(row["alpha_2"])
    index["uk"].add("GB")
    index["u s a"].add("US")
    return index


def country(value: str):
    codes = country_index().get(normalize(value), set())
    return (
        next((row for row in countries() if row["alpha_2"] in codes), None)
        if len(codes) == 1
        else None
    )


@cache
def concept_index(kind):
    index = defaultdict(set)
    for key, aliases in ALIASES.get(kind, {}).items():
        for alias in aliases:
            index[normalize(alias)].add(key)
    if kind == "language":
        for language in pycountry.languages:
            for attr in (
                "name",
                "common_name",
                "inverted_name",
                "alpha_2",
                "alpha_3",
                "bibliographic",
            ):
                if value := getattr(language, attr, None):
                    index[normalize(value)].add(language.alpha_3)
    if kind == "region":
        for region in pycountry.subdivisions.get(country_code="GH"):
            for value in (
                region.code,
                region.code[3:],
                region.name,
                f"{region.name} region",
            ):
                index[normalize(value)].add(region.code)
    if kind == "month":
        for number in range(1, 13):
            for value in (
                str(number),
                f"{number:02}",
                calendar.month_name[number],
                calendar.month_abbr[number],
            ):
                index[normalize(value)].add(str(number))
    return index


def canonical(value: str, kind: str) -> str | None:
    if kind == "country":
        item = country(value)
        if item:
            return item["alpha_2"]
    text = normalize(value)
    keys = concept_index(kind).get(text, set())
    if len(keys) == 1:
        return next(iter(keys))
    parts = [part.strip() for part in re.split(r"[/()]|\s+-\s+", value) if part.strip()]
    if len(parts) > 1:
        meanings = {canonical(part, kind) for part in parts}
        if None not in meanings and len(meanings) == 1:
            return next(iter(meanings))
    if kind == "title":
        return (
            canonical(text.replace(" ", ""), kind)
            if " " in text and len(text) <= 6
            else None
        )
    if kind == "degree":
        prefixes = {
            key
            for alias, candidates in concept_index(kind).items()
            if text.startswith((alias + " in ", alias + " of "))
            for key in candidates
        }
        return next(iter(prefixes)) if len(prefixes) == 1 else None
    return None


def concept_kind(path: str, label: str = "") -> str:
    if path in COUNTRY_PATHS:
        return "country"
    if path.endswith("gender") or path == "gender":
        return "gender"
    if path.endswith("qualification"):
        return "degree"
    if path.endswith(("women_led", "youth_led", "is_founder", ".current")):
        return "boolean"
    if path == "languages.language":
        return "language"
    if path == "languages.level":
        return "proficiency"
    if path == "stage":
        return "stage"
    text = normalize(label)
    for kind, pattern in (
        ("gender", r"\b(?:gender|sex)\b"),
        ("country", r"\b(?:country|nationality|citizenship)\b"),
        ("degree", r"\b(?:degree|qualification)\b"),
        ("employment", r"\b(?:employment|contract|job) type\b"),
        ("proficiency", r"\b(?:proficiency|language level)\b"),
        ("language", r"\blanguages?\b"),
        ("region", r"\bregion\b"),
        ("month", r"\bmonth\b"),
        ("title", r"^(?:(?:honorific|courtesy|salutation) )?title$|^salutation$"),
        ("boolean", r"\b(?:consent|agree|agreement)\b"),
    ):
        if re.search(pattern, text):
            return kind
    return ""
