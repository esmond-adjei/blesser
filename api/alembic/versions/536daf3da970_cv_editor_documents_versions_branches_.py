"""cv editor documents versions branches proposals

Revision ID: 536daf3da970
Revises: 1fa9ccfb410e
Create Date: 2026-10-06 00:28:15.046563

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '536daf3da970'
down_revision: str | Sequence[str] | None = '1fa9ccfb410e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('cv_documents',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('format', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('original_sha256', sa.String(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('fidelity_class', sa.String(), nullable=False),
    sa.Column('head_version_id', sa.String(), nullable=True),
    sa.Column('redo_stack', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('cv_branches',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('document_id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('target_context', sa.JSON(), nullable=False),
    sa.Column('base_version_id', sa.String(), nullable=False),
    sa.Column('head_version_id', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['cv_documents.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'name', name='uq_cv_branch_doc_name')
    )
    op.create_index(op.f('ix_cv_branches_document_id'), 'cv_branches', ['document_id'], unique=False)
    op.create_table('cv_proposals',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('document_id', sa.String(), nullable=False),
    sa.Column('base_version_id', sa.String(), nullable=False),
    sa.Column('branch_id', sa.String(), nullable=False),
    sa.Column('operations_json', sa.JSON(), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('verification_json', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['cv_documents.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cv_proposals_document_id'), 'cv_proposals', ['document_id'], unique=False)
    op.create_index(op.f('ix_cv_proposals_status'), 'cv_proposals', ['status'], unique=False)
    op.create_table('cv_versions',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('document_id', sa.String(), nullable=False),
    sa.Column('parent_version_id', sa.String(), nullable=True),
    sa.Column('branch_id', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('file_path', sa.Text(), nullable=False),
    sa.Column('ir_json', sa.JSON(), nullable=False),
    sa.Column('operations_json', sa.JSON(), nullable=False),
    sa.Column('quality_report_json', sa.JSON(), nullable=False),
    sa.Column('label', sa.String(), nullable=False),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['cv_documents.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cv_versions_branch_id'), 'cv_versions', ['branch_id'], unique=False)
    op.create_index(op.f('ix_cv_versions_document_id'), 'cv_versions', ['document_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cv_versions_document_id'), table_name='cv_versions')
    op.drop_index(op.f('ix_cv_versions_branch_id'), table_name='cv_versions')
    op.drop_table('cv_versions')
    op.drop_index(op.f('ix_cv_proposals_status'), table_name='cv_proposals')
    op.drop_index(op.f('ix_cv_proposals_document_id'), table_name='cv_proposals')
    op.drop_table('cv_proposals')
    op.drop_index(op.f('ix_cv_branches_document_id'), table_name='cv_branches')
    op.drop_table('cv_branches')
    op.drop_table('cv_documents')
