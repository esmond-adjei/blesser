from datetime import UTC, date, datetime

import pytest

from api.autofill import concepts
from api.autofill.matcher import deterministic, match_options
from api.autofill.schemas import FormField


def field(label, **kwargs):
    return FormField(key="f", label=label, **kwargs)


@pytest.mark.parametrize(
    "gender,option",
    [
        ("Male", "Man"),
        ("Female", "Woman"),
        ("M", "Man"),
        ("masculine", "Man"),
        ("Nonbinary", "Non-binary"),
        ("Decline to self-identify", "Prefer not to say"),
    ],
)
def test_gender_concepts(gender, option):
    target = field(
        "Gender",
        type="radio",
        options=[
            {"label": value, "value": value}
            for value in ("Man", "Woman", "Non-binary", "Prefer not to say")
        ],
    )
    result = deterministic(target, {"gender": gender}, {}, {})
    assert (result.value, result.rule, result.confidence) == (
        option,
        "concept:gender",
        "high",
    )


@pytest.mark.parametrize(
    "label,section,path,value",
    [
        (
            "Country of Institution",
            "Personal information",
            "education.country",
            "Ghana",
        ),
        ("Institution country", "", "education.country", "Ghana"),
        ("Country", "University details", "education.country", "Ghana"),
        (
            "Email of referee",
            "Contact information",
            "references.email",
            "ref@example.com",
        ),
        ("Name of organization", "Personal information", "name", "Project"),
        ("Phone", "Referee 1", "references.phone", "+233201234567"),
        ("Country of birth", "University details", "country_of_birth", "Nigeria"),
        ("Place of birth", "", "place_of_birth", "Lagos"),
        ("Institution of referee", "Education", "references.institution", None),
        ("Country of employer", "", "experience.country", None),
    ],
)
def test_label_head_and_qualifier(label, section, path, value):
    profile = {
        "country_of_birth": "Nigeria",
        "place_of_birth": "Lagos",
        "email": "personal@example.com",
        "country_of_residence": "Canada",
        "education": [{"institution": "University of Ghana", "country": "Ghana"}],
        "references": [
            {"name": "Referee", "email": "ref@example.com", "phone": "+233201234567"}
        ],
    }
    result = deterministic(
        field(
            label,
            section=section,
            autocomplete="country-name" if "Country" in label else "",
        ),
        profile,
        {"name": "Project"},
        {},
    )
    if value is None:
        assert result is None
    else:
        assert (result.value, result.rule) == (value, f"qualifier:{path}")


def test_country_data_covers_all_countries_without_guessing_ambiguous_demonyms():
    rows = concepts.countries()
    assert len(rows) == 250
    assert {row["alpha_2"] for row in rows} >= {
        "GH",
        "CI",
        "US",
        "GB",
        "XK",
        "JP",
        "BR",
        "TL",
    }
    for row in rows:
        for value in (
            row["alpha_2"],
            row["alpha_3"],
            row["numeric"],
            *row["names"],
            *row["demonyms"],
        ):
            if not value:
                continue
            codes = concepts.country_index()[concepts.normalize(value)]
            assert row["alpha_2"] in codes
            result = concepts.country(value)
            if len(codes) == 1:
                assert result["alpha_2"] == row["alpha_2"]
            else:
                assert result is None
    assert concepts.country("Ivorian")["alpha_2"] == "CI"
    assert concepts.country("Congolese") is None


@pytest.mark.parametrize(
    "value,path,label,option",
    [
        ("Ivorian", "nationality", "Nationality", "Côte d'Ivoire"),
        ("B.Sc.", "education.qualification", "Degree", "Undergraduate"),
        ("MPhil", "highest_qualification", "Highest qualification", "Master's"),
        ("PhD", "education.qualification", "Degree", "Doctorate"),
        ("yes", "women_led", "Women-led", "I agree"),
        ("no", "", "Consent", "I do not consent"),
        ("FT", "custom_fields", "Employment type", "Full-time"),
        ("eng", "languages.language", "Language", "English"),
        ("fre", "languages.language", "Language", "French"),
        ("fluent", "languages.level", "Proficiency", "C1"),
        ("native", "languages.level", "Proficiency", "Native or bilingual proficiency"),
        ("04", "", "Month", "April"),
        ("Doctor", "custom_fields", "Title", "Dr."),
        ("GH-AH", "custom_fields", "Region", "Ashanti Region"),
    ],
)
def test_canonical_option_families(value, path, label, option):
    assert (
        match_options(
            value, field(label, options=[{"label": option, "value": "chosen"}]), path
        )
        == "chosen"
    )


def test_all_ghana_regions_and_multiple_choices():
    regions = concepts.concept_index("region")
    codes = {code for values in regions.values() for code in values}
    assert len(codes) == 16
    for code in codes:
        assert concepts.canonical(code, "region") == code
    target = field(
        "Language",
        type="checkbox",
        options=[
            {"label": "English", "value": "en"},
            {"label": "French", "value": "fr"},
        ],
    )
    assert match_options(["eng", "fra"], target, "languages.language") == ["en", "fr"]


def test_option_order_canonical_then_normalized_then_tokens_and_ambiguity():
    target = field(
        "Gender",
        options=[
            {"label": "Male", "value": "female"},
            {"label": "Female", "value": "other"},
        ],
    )
    assert match_options("female", target, "gender") == "other"
    target = field(
        "Specialty",
        options=[{"label": "Quality assurance automation engineer QA", "value": "qa"}],
    )
    assert match_options("Quality assurance automation engineer", target) == "qa"
    target = field(
        "Gender",
        options=[{"label": "Male", "value": "m"}, {"label": "Man", "value": "man"}],
    )
    assert match_options("Male", target, "gender") is None
    target = field("Gender", options=[{"label": "Woman", "value": "Male"}])
    assert match_options("Male", target, "gender") is None


@pytest.mark.parametrize(
    "label,profile,expected,rule",
    [
        ("Country of birth", {"nationality": "Ghanaian"}, "Ghana", "nationality"),
        ("Citizenship", {"nationality": "Ivorian"}, "Ivory Coast", "nationality"),
        ("Nationality", {"country_of_birth": "GH"}, "Ghanaian", "country_of_birth"),
        (
            "Current role",
            {
                "experience": [
                    {"role": "Old", "current": False},
                    {"role": "Engineer", "current": True},
                ]
            },
            "Engineer",
            "experience.current",
        ),
        (
            "Current company",
            {"experience": [{"organization": "Employer", "current": True}]},
            "Employer",
            "experience.current",
        ),
        (
            "Highest qualification",
            {"education": [{"qualification": "PhD"}, {"qualification": "BSc"}]},
            "PhD",
            "education",
        ),
        (
            "Full address",
            {
                "address_line1": "1 Main St",
                "city": "Accra",
                "country_of_residence": "Ghana",
            },
            "1 Main St, Accra, Ghana",
            "address_parts",
        ),
    ],
)
def test_inferred_facts_are_medium_confidence(label, profile, expected, rule):
    result = deterministic(field(label), profile, {}, {})
    assert (result.value, result.confidence, result.rule) == (
        expected,
        "medium",
        f"inferred:{rule}",
    )


def test_inferred_birth_country_select_and_explicit_value_precedence():
    target = field(
        "Country of birth",
        tag="select",
        options=[
            {"label": "Ghana", "value": "GH"},
            {"label": "Nigeria", "value": "NG"},
        ],
    )
    result = deterministic(target, {"nationality": "Ghanaian"}, {}, {})
    assert (result.value, result.confidence, result.rule) == (
        "GH",
        "medium",
        "inferred:nationality",
    )
    result = deterministic(
        target, {"nationality": "Ghanaian", "country_of_birth": "Nigeria"}, {}, {}
    )
    assert (result.value, result.confidence) == ("NG", "high")


def test_age_from_birth_date_and_ambiguous_inferences():
    today = datetime.now(UTC).date()
    birthday = date(today.year - 25, today.month, today.day)
    result = deterministic(
        field("Age", type="number"), {"date_of_birth": birthday.isoformat()}, {}, {}
    )
    assert (result.value, result.rule, result.confidence) == (
        "25",
        "inferred:date_of_birth",
        "medium",
    )
    for label, profile in [
        ("Country of birth", {"nationality": "Congolese"}),
        (
            "Current employer",
            {
                "experience": [
                    {"organization": "A", "current": True},
                    {"organization": "B", "current": True},
                ]
            },
        ),
        (
            "Highest qualification",
            {"education": [{"qualification": "Unknown"}, {"qualification": "BSc"}]},
        ),
        ("Age", {"date_of_birth": "invalid"}),
    ]:
        assert deterministic(field(label), profile, {}, {}) is None


def test_language_checkbox_and_combined_option_names():
    target = field(
        "Languages",
        type="checkbox",
        options=[
            {"label": "English (en)", "value": "english"},
            {"label": "French / français", "value": "fr"},
        ],
    )
    result = deterministic(
        target, {"languages": [{"language": "eng", "level": "fluent"}]}, {}, {}
    )
    assert (result.value, result.rule) == (["english"], "concept:language")
    assert (
        match_options(
            "Male",
            field("Gender", options=[{"label": "Man / Male", "value": "m"}]),
            "gender",
        )
        == "m"
    )
    assert (
        match_options(
            "GH",
            field("Country", options=[{"label": "Ghana (GH)", "value": "country-id"}]),
            "country_of_residence",
        )
        == "country-id"
    )


def test_section_current_employment_uses_current_record_among_multiple_rows():
    profile = {
        "experience": [
            {"role": "Old", "organization": "Old employer", "current": False},
            {"role": "Engineer", "organization": "Current employer", "current": True},
        ]
    }
    for label, expected in [
        ("Job title", "Engineer"),
        ("Employer", "Current employer"),
    ]:
        result = deterministic(
            field(label, section="Current employment"), profile, {}, {}
        )
        assert (result.value, result.confidence, result.rule) == (
            expected,
            "medium",
            "inferred:experience.current",
        )


@pytest.mark.parametrize(
    "birthday,expected",
    [("2000-11-09", "26"), ("2000-11-10", "26"), ("2000-11-11", "25")],
)
def test_age_respects_birthday_boundary(monkeypatch, birthday, expected):
    from api.autofill import matcher

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 10, tzinfo=UTC)

    monkeypatch.setattr(matcher, "datetime", FixedDateTime)
    assert (
        deterministic(field("Age"), {"date_of_birth": birthday}, {}, {}).value
        == expected
    )
