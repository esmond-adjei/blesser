import sqlalchemy as sa

from alembic import op

revision = "0007_scan_finds"
down_revision = "0006_autofill_v2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scan_finds",
        sa.Column(
            "scan_id",
            sa.String(),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "opportunity_id",
            sa.String(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("found_at", sa.DateTime(), nullable=False),
        sa.Column("source_url", sa.Text()),
    )
    op.create_index("ix_scan_finds_opportunity_id", "scan_finds", ["opportunity_id"])
    op.execute("""
        INSERT INTO scan_finds (scan_id, opportunity_id, found_at, source_url)
        SELECT scan_id, id, created_at, source_url FROM opportunities WHERE scan_id IS NOT NULL
    """)
    op.execute("""
        WITH task_logs AS (
            SELECT scan_id, created_at,
                CASE WHEN pg_input_is_valid(log, 'jsonb') THEN log::jsonb END AS trace
            FROM scan_tasks
            WHERE log IS NOT NULL
        ),
        saves AS (
            SELECT scan_id,
                CASE WHEN pg_input_is_valid(event->>'at', 'timestamp')
                    THEN (event->>'at')::timestamp ELSE created_at END AS found_at,
                CASE WHEN pg_input_is_valid(event->>'result_preview', 'jsonb')
                    THEN (event->>'result_preview')::jsonb END AS result
            FROM task_logs
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE WHEN jsonb_typeof(trace) = 'array' THEN trace ELSE '[]'::jsonb END
            ) AS events(event)
            WHERE event->>'tool' = 'save_opportunity' AND event->'ok' = 'true'::jsonb
        )
        INSERT INTO scan_finds (scan_id, opportunity_id, found_at)
        SELECT saves.scan_id, opportunities.id, min(saves.found_at)
        FROM saves
        JOIN opportunities ON opportunities.id = saves.result->>'opportunity_id'
        GROUP BY saves.scan_id, opportunities.id
        ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.drop_table("scan_finds")
