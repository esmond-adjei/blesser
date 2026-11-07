"""Document kind names, for the model and default titles. Mirrored by
webapp/src/components/documents/kinds.ts."""

from api.cv.models import DOCUMENT_KINDS

#: What the model and the student read: "a statement of purpose".
NOUNS = {
    "cv": "CV",
    "sop": "statement of purpose",
    "diversity_statement": "diversity statement",
    "research_proposal": "research proposal",
    "interest": "interest statement",
    "note": "note",
}

DEFAULT_TITLES = {
    "cv": "My CV",
    "sop": "Statement of purpose",
    "diversity_statement": "Diversity statement",
    "research_proposal": "Research proposal",
    "interest": "Interest statement",
    "note": "Note",
}

assert set(NOUNS) == set(DOCUMENT_KINDS) == set(DEFAULT_TITLES)


def noun(kind: str | None) -> str:
    return NOUNS.get(kind or "cv", "document")
