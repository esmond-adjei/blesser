from types import SimpleNamespace

import api.agent.tools  # noqa: F401  (app import order: tools before prospects.tools)
from api.core.textnorm import canonical_openalex_id, normalize_text
from api.prospects import grounding
from api.prospects.tools import verify_professor_save

AID = "https://openalex.org/A5023888391"
ABSTRACT = (
    "We introduce Schrödinger bridges as a principled framework for generative "
    "modeling, connecting optimal transport with diffusion processes and "
    "showing strong results on image synthesis benchmarks."
)
WORKS = [
    {"title": "Schrödinger Bridges for Generative Modeling", "abstract": ABSTRACT},
    {"title": "Deep-Learning-Based Segmentation of Retinal Vessels", "abstract": ""},
    {
        "title": "Room-temperature <i>in situ</i> growth of MoS<sub>2</sub>",
        "abstract": "",
    },
    {"title": "Introduction", "abstract": ""},
]


def _ctx(score=0.6123, texts=(ABSTRACT,)):
    ctx = SimpleNamespace()
    grounding.record_author_candidates(
        ctx, [{"openalex_id": AID, "institution": "MIT"}]
    )
    grounding.record_works(ctx, AID, WORKS)
    grounding.record_score(ctx, list(texts), {"score": score})
    return ctx


def _save(ctx, **overrides):
    body = {
        "openalex_id": AID,
        "papers": [{"title": "Schrödinger Bridges for Generative Modeling"}],
        "similarity_score": 0.61,
    }
    body.update(overrides)
    return grounding.ground_professor_save(body, ctx, "MIT")


def test_normaliser_and_ids():
    assert normalize_text("Deep-Learning-Based") == "deep learning based"
    assert normalize_text("Schrödinger") == "schrodinger"
    assert normalize_text("growth of MoS<sub>2</sub>") == "growth of mos2"
    assert canonical_openalex_id(AID) == canonical_openalex_id("a5023888391")


def test_short_id_saves_and_keeps_openalex_form():
    error, grounded = _save(_ctx(), openalex_id="A5023888391")
    assert error is None
    assert grounded["openalex_id"] == AID


def test_accents_and_markup_in_titles_match_plain_text():
    error, _ = _save(
        _ctx(), papers=[{"title": "Schrodinger Bridges for Generative Modeling"}]
    )
    assert error is None
    error, _ = _save(
        _ctx(), papers=[{"title": "Room-temperature in situ growth of MoS2"}]
    )
    assert error is None


def test_excerpted_or_joined_abstracts_still_ground_the_score():
    first_sentence = ABSTRACT.split(",")[0] + "..."
    joined = f"Schrödinger Bridges for Generative Modeling. {ABSTRACT}"
    one_word_changed = ABSTRACT.replace("strong", "excellent")
    for text in (first_sentence, joined, one_word_changed):
        error, _ = _save(_ctx(texts=(text,)))
        assert error is None, text


def test_unrelated_text_still_cannot_ground_a_score():
    error, _ = _save(_ctx(texts=("Large language models for legal contract review.",)))
    assert error and "never estimate" in error


def test_rounded_score_is_accepted_and_stored_as_computed():
    error, grounded = _save(_ctx(score=0.6123), similarity_score=0.6)
    assert error is None and grounded["similarity_score"] == 0.6123
    error, _ = _save(_ctx(score=0.6123), similarity_score=0.75)
    assert error and "never estimate" in error


def test_a_long_invented_title_cannot_borrow_a_short_real_one():
    error, _ = _save(
        _ctx(),
        papers=[{"title": "An Introduction to Diffusion Models for Drug Design"}],
    )
    assert error and "not returned by get_author_works" in error
    error, _ = _save(_ctx(), papers=[{"title": "Schrödinger Bridges for Generative"}])
    assert error is None


def test_rationale_check_ignores_hyphens_accents_and_markup():
    for title, rationale in [
        (
            "Deep-Learning-Based Segmentation of Retinal Vessels",
            "Their deep learning based segmentation of retinal vessels work fits.",
        ),
        (
            "Schrödinger Bridges for Generative Modeling",
            "Their Schrodinger bridges for generative modeling paper fits.",
        ),
        (
            "Room-temperature <i>in situ</i> growth of MoS<sub>2</sub>",
            "Their room temperature in situ growth of MoS2 work is relevant.",
        ),
    ]:
        assert (
            verify_professor_save(
                {"papers": [{"title": title}], "rationale": rationale}
            )
            is None
        ), title


def test_restored_snapshots_with_full_url_keys_still_ground():
    ctx = SimpleNamespace()
    snapshot = grounding.snapshot(_ctx())
    snapshot["author_candidates"] = {AID: {"openalex_id": AID, "institution": "MIT"}}
    snapshot["works_by_author"] = {AID: WORKS}
    grounding.restore_from_checkpoint(
        ctx, [{"role": "user", grounding.CHECKPOINT_KEY: snapshot}]
    )
    error, _ = _save(ctx)
    assert error is None
