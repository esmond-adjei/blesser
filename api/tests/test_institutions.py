import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from api.prospects import grounding, institutions, openalex

THIS_YEAR = datetime.now(UTC).year


@pytest.mark.parametrize(
    "author_inst,school",
    [
        ("Massachusetts Institute of Technology", "MIT"),
        ("University College London", "UCL"),
        ("Carnegie Mellon University", "CMU"),
        ("University of California, Los Angeles", "UCLA"),
        ("École Polytechnique Fédérale de Lausanne", "EPFL"),
        ("Kwame Nkrumah University of Science and Technology", "KNUST"),
        ("National University of Singapore", "NUS"),
        ("Université de Montréal", "University of Montreal"),
        ("Universität Zürich", "University of Zurich"),
        ("University of Toronto", "Toronto"),
    ],
)
def test_names_that_used_to_be_refused_now_match(author_inst, school):
    assert grounding._institution_matches(author_inst, school)


def test_alternative_names_from_openalex_match():
    assert grounding._institution_matches(
        "Technische Universität München",
        "Technical University of Munich",
        school_names=[
            "Technical University of Munich",
            "Technische Universität München",
            "TUM",
        ],
    )


def test_with_ids_a_different_institution_is_refused():
    ubc = {
        "institutions": ["University of British Columbia"],
        "institution_ids": ["I141945490"],
    }
    assert not grounding._institution_matches(ubc, "Columbia University", "I78577930")
    bc = {"institutions": ["Boston College"], "institution_ids": ["I111"]}
    assert not grounding._institution_matches(bc, "Boston University", "I222")


def test_with_ids_the_same_institution_or_a_parent_matches():
    at_mit = {
        "institutions": ["Broad Institute"],
        "institution_ids": ["I107606265", "I63966007"],
    }
    assert grounding._institution_matches(at_mit, "MIT", "I63966007")  # lineage
    renamed = {"institutions": ["MIT"], "institution_ids": ["I999"]}
    assert grounding._institution_matches(
        renamed, "Massachusetts Institute of Technology", "I63966007"
    )  # ids disagree, but the names are the same school


def test_any_current_affiliation_matches():
    dual = {
        "institutions": ["Google (United States)", "Stanford University"],
        "institution_ids": ["I1291425158", "I97018004"],
    }
    assert grounding._institution_matches(dual, "Stanford University", "I97018004")


def test_missing_institution_data_never_refuses():
    assert grounding._institution_matches({"institutions": []}, "MIT", "I63966007")
    assert grounding._institution_matches(None, "MIT")


def test_author_institutions_reads_the_current_schema():
    record = {
        "id": "https://openalex.org/A1",
        "display_name": "Ada",
        "last_known_institution": None,
        "last_known_institutions": [
            {
                "id": "https://openalex.org/I1",
                "display_name": "Uni One",
                "lineage": ["https://openalex.org/I1"],
            }
        ],
        "affiliations": [
            {
                "institution": {
                    "id": "https://openalex.org/I2",
                    "display_name": "Hospital Two",
                    "lineage": ["https://openalex.org/I2", "https://openalex.org/I3"],
                },
                "years": [THIS_YEAR - 1],
            },
            {
                "institution": {
                    "id": "https://openalex.org/I9",
                    "display_name": "Old Uni",
                },
                "years": [THIS_YEAR - 15],
            },
        ],
    }
    cand = openalex._candidate(record)
    assert cand["institution"] == "Uni One"
    assert cand["institutions"] == ["Uni One", "Hospital Two"]
    assert cand["institution_ids"] == ["I1", "I2", "I3"]  # Old Uni is not current


def test_clean_person_name():
    assert openalex.clean_person_name("Prof. Dr. Jane Smith, PhD") == "Jane Smith"
    assert openalex.clean_person_name("Jane Smith") == "Jane Smith"


def test_author_search_is_scoped_to_the_school_then_global(monkeypatch):
    calls = []

    async def fake_get(path, params):
        calls.append(dict(params))
        if "filter" in params:
            return {"results": []}  # nobody at the school by that name
        return {
            "results": [{"id": "https://openalex.org/A1", "display_name": "Wei Wang"}]
        }

    monkeypatch.setattr(openalex, "_get_json", fake_get)
    out = asyncio.run(openalex.find_author("Dr. Wei Wang", institution_id="I63966007"))
    assert calls[0] == {
        "search": "Wei Wang",
        "filter": "affiliations.institution.id:I63966007",
        "per_page": 5,
    }
    # Then other spellings at the school, then the global search.
    assert calls[1]["search"] == "Wang Wei" and "filter" in calls[1]
    assert "filter" not in calls[-1] and out[0]["openalex_id"].endswith("A1")


@pytest.mark.institutions
def test_resolve_school_stores_the_lookup_once(monkeypatch):
    lookups = []

    async def find_institution(name):
        lookups.append(name)
        return {
            "id": "I63966007",
            "display_name": "Massachusetts Institute of Technology",
            "names": ["Massachusetts Institute of Technology", "MIT"],
        }

    monkeypatch.setattr(openalex, "find_institution", find_institution)

    class Session:
        async def commit(self):
            pass

    school = SimpleNamespace(
        name="MIT", openalex_institution_id=None, institution_names=None
    )
    first = asyncio.run(institutions.resolve_school(Session(), school))
    second = asyncio.run(institutions.resolve_school(Session(), school))
    assert (
        first
        == second
        == ("I63966007", ["Massachusetts Institute of Technology", "MIT"])
    )
    assert lookups == ["MIT"]
    assert json.loads(school.institution_names)[1] == "MIT"


@pytest.mark.institutions
def test_a_failed_lookup_is_retried_later(monkeypatch):
    async def down(name):
        raise openalex.OpenAlexUnavailable("down")

    monkeypatch.setattr(openalex, "find_institution", down)
    school = SimpleNamespace(
        name="MIT", openalex_institution_id=None, institution_names=None
    )
    assert asyncio.run(institutions.resolve_school(None, school)) == (None, [])
    assert school.institution_names is None  # not stored: try again next time
