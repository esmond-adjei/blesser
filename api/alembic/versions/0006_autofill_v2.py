import sqlalchemy as sa

from alembic import op

revision = "0006_autofill_v2"
down_revision = "0005_autofill"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE applicant_profiles
        SET data = ('{"country_of_birth":"","place_of_birth":""}'::jsonb || data::jsonb)::json
    """)
    op.create_table(
        "autofill_corrections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("host", sa.String(253), nullable=False),
        sa.Column("label", sa.String(4000), nullable=False),
        sa.Column("label_key", sa.String(64), nullable=False),
        sa.Column("field_type", sa.String(50), nullable=False),
        sa.Column("descriptor", sa.JSON(), nullable=False),
        sa.Column("filled", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("wrong_field", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "user_id", "host", "label_key", "field_type", name="uq_autofill_correction"
        ),
    )
    op.create_index(
        "ix_autofill_corrections_user_id", "autofill_corrections", ["user_id"]
    )
    op.create_table(
        "autofill_reports",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.JSON(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(4000), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_autofill_reports_user_id", "autofill_reports", ["user_id"])


def downgrade():
    op.drop_table("autofill_reports")
    op.drop_table("autofill_corrections")
    op.execute(
        "UPDATE applicant_profiles SET data = (data::jsonb - 'country_of_birth' - 'place_of_birth')::json"
    )
