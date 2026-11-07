"""Draft claim checks refuse inventions, not ordinary cold emails."""

from types import SimpleNamespace

import pytest

from api.outreach.draft_check import known_facts_for, target_names_for, verify_draft

TITLE = "Equivariant message passing for molecular graphs"
FACTS = known_facts_for(
    SimpleNamespace(
        degree_level="phd",
        field="Computer Science",
        interest_statement="LLM reasoning and graph neural networks for drug discovery",
    )
)
TARGETS = target_names_for("Carnegie Mellon University", "Jane Smith", "Smith Lab")
BASE = f"Dear Professor Smith, your paper {TITLE} shaped my thinking. "


def _check(sentence: str, context: str = ""):
    return verify_draft("PhD", BASE + sentence, [TITLE], FACTS, TARGETS, context)


@pytest.mark.parametrize(
    "sentence",
    [
        "Please find my CV attached.",
        "I have attached my CV.",
        "Moreover, I would love to apply these ideas to protein design.",
        "Furthermore, I am curious whether the approach scales.",
        "Given my interest in drug discovery, this work resonated with me.",
        "Thus, I believe my interests align closely with the lab.",
        "I am fascinated by Large Language Models and how they reason.",
        "The NeurIPS paper on equivariant message passing caught my attention.",
        "I would love to experiment with PyTorch Geometric on this problem.",
        "Inspired by AlphaFold, I want to study protein structure prediction.",
        "My goal is to work on Bayesian methods for Molecular Design.",
        "As an aspiring NLP researcher, I found this work exciting.",
        "I hope to join the Robotics Institute at CMU as a PhD student.",
        "I learned about your work from a talk at ICML, which I found inspiring.",
        "I have read several of your recent publications on molecular graphs.",
        "I enjoyed your paper published in Nature Machine Intelligence last year.",
        "In the next five years, I hope to build tools for chemists.",
    ],
)
def test_ordinary_sentences_pass(sentence):
    assert _check(sentence) is None


@pytest.mark.parametrize(
    "sentence",
    [
        "I am a Stanford student.",
        "My alma mater is Stanford University.",
        "Stanford is where I did my undergrad.",
        "I attend Stanford University.",
        "As a CMU graduate, I bring rigour.",
        "I studied at KNUST.",
        "I hope to join your lab as a former Stanford student.",
        "I spent last summer at Google DeepMind.",
        "I admire your work, and Stanford is my alma mater.",
        "The applicant has a GPA of 3.9.",
        "I have published two papers on molecular graphs.",
        "I published two papers on your topic.",
        "I have three years of industry experience.",
        "I work at a robotics startup.",
    ],
)
def test_invented_background_is_still_refused(sentence):
    assert _check(sentence), sentence


def test_names_from_the_professors_abstracts_are_known():
    sentence = "During my internship I used AlphaFold Multimer for protein docking."
    assert _check(sentence)  # an unknown system in a background clause
    abstract = "We extend AlphaFold Multimer to model protein complexes."
    assert _check(sentence, context=abstract) is None
