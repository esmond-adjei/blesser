"""Scheduled listing checks, cycle-aware dedupe keys, organization aliases, duplicate review.

Recomputes every `opportunities.dedupe_key` with the cycle-aware normalization in
`api/opportunities/dedupe.py` (frozen below, so later edits there do not change what this
migration did). Rows that now share a key are not merged here: the best row takes the key
and the others keep `<key>#<id>`, so staff see them in the possible-duplicates list and
merge them by hand.
"""

import re

import sqlalchemy as sa

from alembic import op

revision = "0009_listing_freshness"
down_revision = "0008_assistant"
branch_labels = None
depends_on = None

# Canonical names for organizations that are written in unrelated ways.
SEED_ALIASES = {
    "german academic exchange service": "daad",
    "deutscher akademischer austauschdienst": "daad",
    "gates": "bill melinda gates",
    "bill and melinda gates": "bill melinda gates",
    "tony elumelu": "tef",
    "national entrepreneurship and innovation programme": "neip",
    "national entrepreneurship and innovation program": "neip",
    "kwame nkrumah university of science and technology": "knust",
    "university of ghana legon": "university of ghana",
    "getfund": "ghana education",
    "african development bank group": "african development bank",
    "afdb": "african development bank",
}

_PUNCTUATION = re.compile(r"[^a-z0-9 ]")
_SPACES = re.compile(r"\s+")
_YEARS = re.compile(r"\b(?:19|20)\d{2}(?:\s*[/-]\s*(?:19|20)?\d{2})?\b")
_ORDINAL = r"(?:\d+(?:st|nd|rd|th)?|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
_CYCLE_WORDS = r"(?:call|cohort|round|intake|edition|cycle|batch)"
_CYCLE_PHRASES = (
    re.compile(
        r"\b(?:open )?call for (?:applications|proposals|entries|nominations|submissions|participants)\b"
    ),
    re.compile(r"\b(?:applications? (?:are )?(?:now )?open|now open|apply now)\b"),
    re.compile(rf"\b(?:{_ORDINAL} )?{_CYCLE_WORDS}(?: {_ORDINAL})?\b"),
)
_ORG_FILLER = {
    "foundation",
    "trust",
    "fund",
    "inc",
    "incorporated",
    "ltd",
    "limited",
    "llc",
    "plc",
    "gmbh",
    "org",
    "organisation",
    "organization",
}
_STATUS_RANK = {"published": 0, "archived": 1, "in_review": 2, "draft": 3, "hidden": 4}


def _normalize(value):
    return _SPACES.sub(" ", _PUNCTUATION.sub(" ", (value or "").lower())).strip()


def _key(organization, title):
    words = _normalize(organization).split()
    if words[:1] == ["the"]:
        words = words[1:]
    while len(words) > 1 and words[-1] in _ORG_FILLER:
        words.pop()
    org = " ".join(words)
    org = SEED_ALIASES.get(org, org)
    plain = _normalize(title)
    stripped = _normalize(_YEARS.sub(" ", (title or "").lower()))
    for pattern in _CYCLE_PHRASES:
        stripped = pattern.sub(" ", stripped)
    stripped = _SPACES.sub(" ", stripped).strip()
    return f"{org}|{stripped or plain}"


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column("opportunities", sa.Column("checked_at", sa.DateTime()))
    op.add_column(
        "opportunities",
        sa.Column("check_outcome", sa.String(), server_default="", nullable=False),
    )
    op.add_column(
        "opportunities",
        sa.Column("source_hash", sa.String(), server_default="", nullable=False),
    )
    op.create_index("ix_opportunities_checked_at", "opportunities", ["checked_at"])
    op.create_index(
        "ix_opportunities_title_trgm",
        "opportunities",
        [sa.text("lower(title) gin_trgm_ops")],
        postgresql_using="gin",
    )
    op.create_index("ix_opportunities_source_url", "opportunities", ["source_url"])
    op.create_table(
        "organization_aliases",
        sa.Column("alias", sa.String(), primary_key=True),
        sa.Column("canonical", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "duplicate_dismissals",
        sa.Column(
            "first_id",
            sa.String(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "second_id",
            sa.String(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "dismissed_by",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("first_id < second_id", name="ck_duplicate_dismissal_order"),
    )
    aliases = sa.table(
        "organization_aliases", sa.column("alias"), sa.column("canonical")
    )
    op.bulk_insert(
        aliases, [{"alias": a, "canonical": c} for a, c in SEED_ALIASES.items()]
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, organization, title, status, verified_at, created_at, dedupe_key "
            "FROM opportunities"
        )
    ).mappings()
    groups: dict[str, list] = {}
    for row in rows:
        groups.setdefault(_key(row["organization"], row["title"]), []).append(row)
    updates = []
    for key, members in groups.items():
        members.sort(
            key=lambda r: (
                _STATUS_RANK.get(r["status"], 9),
                -(r["verified_at"].timestamp() if r["verified_at"] else 0),
                r["created_at"].timestamp() if r["created_at"] else 0,
                r["id"],
            )
        )
        for index, row in enumerate(members):
            new = key if index == 0 else f"{key}#{row['id']}"
            if new != row["dedupe_key"]:
                updates.append({"id": row["id"], "key": new})
    if updates:
        # Park every changed key first so a swap between two rows never trips the unique index.
        bind.execute(
            sa.text(
                "UPDATE opportunities SET dedupe_key = '#migrating#' || id WHERE id = :id"
            ),
            [{"id": u["id"]} for u in updates],
        )
        bind.execute(
            sa.text("UPDATE opportunities SET dedupe_key = :key WHERE id = :id"),
            updates,
        )


def downgrade():
    # Keys stay in the new form: the old form is a subset of what they identify.
    op.drop_table("duplicate_dismissals")
    op.drop_table("organization_aliases")
    op.drop_index("ix_opportunities_source_url", table_name="opportunities")
    op.drop_index("ix_opportunities_title_trgm", table_name="opportunities")
    op.drop_index("ix_opportunities_checked_at", table_name="opportunities")
    op.drop_column("opportunities", "source_hash")
    op.drop_column("opportunities", "check_outcome")
    op.drop_column("opportunities", "checked_at")
