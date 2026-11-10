import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.applicant_kit.schemas import ProfileIn, ProjectIn
from api.autofill.matcher import deterministic, document_match, free_text, match_options
from api.autofill.schemas import FillRequest, FormField
from api.autofill.vocabulary import SYNONYMS

FIXTURES = Path(__file__).parent / "fixtures" / "autofill"
KIT = json.loads((FIXTURES / "kit.json").read_text())
FORMS = [
    json.loads(path.read_text())
    for path in sorted(FIXTURES.glob("*.json"))
    if path.stem != "kit"
]
CASES = [(form, row) for form in FORMS for row in form["fields"]]


@pytest.mark.parametrize(
    ("form", "row"), CASES, ids=[f"{form['name']}:{row['key']}" for form, row in CASES]
)
def test_realistic_field_corpus(form, row):
    field = FormField.model_validate(
        {key: value for key, value in row.items() if key != "expected"}
    )
    expected = row["expected"]
    result = deterministic(
        field,
        {**KIT["profile"], **form.get("profile", {})},
        KIT["project"],
        KIT["profile"]["sensitive"],
    ) or document_match(field, KIT["documents"])
    if expected is None or expected["source"] == "drafted":
        assert result is None
        if expected:
            assert free_text(field)
    else:
        assert result is not None
        for key, value in expected.items():
            assert getattr(result, key) == value


def test_vocabulary_covers_every_writable_profile_and_project_field():
    assert set(ProfileIn.model_fields) - {"sensitive"} <= set(SYNONYMS["en"]["profile"])
    assert set(ProjectIn.model_fields) <= set(SYNONYMS["en"]["project"])


@pytest.mark.parametrize(
    ("profile", "label", "expected"),
    [
        ({"given_name": "Ama", "family_name": "Mensah"}, "Full name", "Ama Mensah"),
        ({"full_name": "Ama Kofi Mensah"}, "First name", "Ama"),
        ({"full_name": "Ama Kofi Mensah"}, "Surname", "Kofi Mensah"),
    ],
)
def test_names(profile, label, expected):
    assert (
        deterministic(FormField(key="f", label=label), profile, {}, {}).value
        == expected
    )


@pytest.mark.parametrize(
    ("value", "path", "options", "expected"),
    [
        ("GB", "country_of_residence", [("United Kingdom", "uk")], "uk"),
        ("Ghanaian", "nationality", [("Ghana", "GH")], "GH"),
        ("United States", "country_of_residence", [("USA", "US")], "US"),
        ("Fémale", "gender", [("Female", "f")], "f"),
        ("Yes", "women_led", [("YES", "1"), ("No", "0")], "1"),
        ("No", "women_led", [("Yes", "1"), ("NO", "0")], "0"),
        ("Ghana", "country_of_residence", [("Nigeria", "NG")], None),
        ("Ghana", "country_of_residence", [("Ghana", "1"), ("Ghana", "2")], None),
    ],
)
def test_option_normalization(value, path, options, expected):
    field = FormField(
        key="f", options=[{"label": label, "value": value} for label, value in options]
    )
    assert match_options(value, field, path) == expected


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        ({"type": "date", "placeholder": "MM/DD/YYYY"}, "1997-04-09"),
        ({"placeholder": "DD.MM.YYYY"}, "09.04.1997"),
        ({"placeholder": "YYYY/MM/DD"}, "1997/04/09"),
        ({"type": "month"}, "1997-04"),
        ({"autocomplete": "bday-day"}, "9"),
        ({"autocomplete": "bday-year"}, "1997"),
        (
            {
                "autocomplete": "bday-month",
                "tag": "select",
                "options": [{"value": "apr", "label": "April"}],
            },
            "apr",
        ),
    ],
)
def test_dates(attributes, expected):
    assert (
        deterministic(
            FormField(key="f", label="Date of birth", **attributes),
            KIT["profile"],
            {},
            {},
        ).value
        == expected
    )


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        ({"autocomplete": "section-contact tel"}, "+233201234567"),
        ({"autocomplete": "tel-national"}, "020 123 4567"),
        ({"autocomplete": "tel-country-code"}, "+233"),
        ({"help_text": "Digits only"}, "233201234567"),
        ({"help_text": "International format"}, "+233 20 123 4567"),
    ],
)
def test_phone_formats(attributes, expected):
    assert (
        deterministic(
            FormField(key="f", type="tel", **attributes), KIT["profile"], {}, {}
        ).value
        == expected
    )


def test_nested_values_use_explicit_index_and_do_not_guess_between_multiple_rows():
    profile = {"references": [{"name": "Ama"}, {"name": "Kojo"}]}
    assert (
        deterministic(
            FormField(key="f", label="Reference name", name="references[1].name"),
            profile,
            {},
            {},
        ).value
        == "Kojo"
    )
    assert (
        deterministic(
            FormField(key="f", label="Reference 2 name"), profile, {}, {}
        ).value
        == "Kojo"
    )
    assert (
        deterministic(FormField(key="f", label="Reference name"), profile, {}, {})
        is None
    )


@pytest.mark.parametrize("accept", [".docx", "image/*", "application/msword"])
def test_document_accept_rejects_incompatible_default(accept):
    assert (
        document_match(
            FormField(key="f", label="Resume", type="file", accept=accept),
            KIT["documents"],
        )
        is None
    )


def test_documents_require_an_identified_kind_and_default():
    assert (
        document_match(
            FormField(key="f", label="Upload", type="file"), KIT["documents"]
        )
        is None
    )
    docs = [{**KIT["documents"][0], "is_default": False}]
    assert document_match(FormField(key="f", label="CV", type="file"), docs) is None


@pytest.mark.parametrize(
    "label",
    [
        "Describe your passport",
        "Passport",
        "Identity number",
        "National identity details",
    ],
)
def test_sensitive_requires_exact_identification(label):
    field = FormField(key="f", label=label, tag="textarea")
    assert (
        deterministic(
            field, KIT["profile"], KIT["project"], KIT["profile"]["sensitive"]
        )
        is None
    )
    assert not free_text(field)


def test_deterministic_limits_do_not_truncate_saved_facts():
    assert (
        deterministic(
            FormField(key="f", label="Short bio", word_limit=2), KIT["profile"], {}, {}
        )
        is None
    )
    assert (
        deterministic(
            FormField(key="f", label="Full name", max_length=2), KIT["profile"], {}, {}
        )
        is None
    )


def test_request_limits_and_trimming():
    req = FillRequest(
        page={"url": " https://example.com/ "},
        fields=[{"key": " f ", "label": " Name "}],
    )
    assert req.fields[0].key == "f" and req.fields[0].label == "Name"
    for fields in (
        [{"key": str(i)} for i in range(301)],
        [{"key": "f"}, {"key": "f"}],
        [{"key": "f", "label": "x" * 4001}],
        [{"key": "f", "options": [{"label": "x", "value": "x"}] * 501}],
    ):
        with pytest.raises(ValidationError):
            FillRequest(page={"url": "https://example.com"}, fields=fields)


@pytest.mark.parametrize(
    ("section", "label", "expected"),
    [
        ("Reference", "Name", "Kojo Boateng"),
        ("Referee", "Email", "kojo@example.com"),
        ("Education", "Country", "Ghana"),
        ("Education", "Start", "2015-09-01"),
        ("Work experience", "Organization", "Example Labs"),
        ("Team", "Name", "Ama Mensah"),
        ("Publication", "Title", "Tools for small businesses"),
    ],
)
def test_section_disambiguates_nested_fields(section, label, expected):
    field = FormField(key="f", label=label, section=section)
    assert deterministic(field, KIT["profile"], KIT["project"], {}).value == expected


def test_date_month_select_by_label_and_two_digit_year():
    field = FormField(
        key="f",
        label="Month of birth",
        tag="select",
        options=[{"label": "April", "value": "apr"}],
    )
    assert deterministic(field, KIT["profile"], {}, {}).value == "apr"
    field = FormField(key="f", label="Date of birth", placeholder="MM/DD/YY")
    assert deterministic(field, KIT["profile"], {}, {}).value == "04/09/97"
