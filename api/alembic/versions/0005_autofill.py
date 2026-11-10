"""Browser sessions, replay detection, answer matching and daily draft budgets."""

import re
import unicodedata

import sqlalchemy as sa

from alembic import op

revision = "0005_autofill"
down_revision = "0004_applicant_kit"
branch_labels = None
depends_on = None


def normalized_question(value):
    value = re.sub(
        r"\b(?:max(?:imum)?|up to|limit(?:ed)? to)\s+\d+\s+words?\b",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"linkedin|github", lambda match: match[0].lower(), value, flags=re.IGNORECASE
    )
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w]+|_", " ", value).split())


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "auth_extension_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_auth_extension_sessions_user_id", "auth_extension_sessions", ["user_id"]
    )
    op.add_column(
        "auth_refresh_tokens",
        sa.Column("extension_session_id", sa.String(), nullable=True),
    )
    op.add_column(
        "auth_refresh_tokens", sa.Column("used_at", sa.DateTime(), nullable=True)
    )
    op.create_foreign_key(
        "fk_refresh_extension_session",
        "auth_refresh_tokens",
        "auth_extension_sessions",
        ["extension_session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_auth_refresh_tokens_extension_session_id",
        "auth_refresh_tokens",
        ["extension_session_id"],
    )
    op.create_table(
        "autofill_daily_usage",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("drafted_fields", sa.Integer(), nullable=False),
        sa.CheckConstraint("drafted_fields >= 0", name="ck_autofill_usage"),
    )
    op.add_column(
        "applicant_answers",
        sa.Column("normalized_question", sa.Text(), nullable=False, server_default=""),
    )
    connection = op.get_bind()
    answers = connection.execute(sa.text("SELECT id, question FROM applicant_answers"))
    for answer_id, question in answers:
        connection.execute(
            sa.text(
                "UPDATE applicant_answers SET normalized_question = :question WHERE id = :id"
            ),
            {"id": answer_id, "question": normalized_question(question)},
        )
    op.alter_column("applicant_answers", "normalized_question", server_default=None)
    op.create_index(
        "ix_applicant_answers_normalized_question",
        "applicant_answers",
        ["normalized_question"],
        postgresql_using="gin",
        postgresql_ops={"normalized_question": "gin_trgm_ops"},
    )


def downgrade():
    op.drop_index(
        "ix_applicant_answers_normalized_question", table_name="applicant_answers"
    )
    op.drop_column("applicant_answers", "normalized_question")
    op.drop_table("autofill_daily_usage")
    op.drop_index(
        "ix_auth_refresh_tokens_extension_session_id", table_name="auth_refresh_tokens"
    )
    op.drop_constraint(
        "fk_refresh_extension_session", "auth_refresh_tokens", type_="foreignkey"
    )
    op.drop_column("auth_refresh_tokens", "used_at")
    op.drop_column("auth_refresh_tokens", "extension_session_id")
    op.drop_table("auth_extension_sessions")
