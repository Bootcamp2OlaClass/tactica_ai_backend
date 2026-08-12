"""add structured extraction tables

Revision ID: 49d583811887
Revises: 644fc5acdae4
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '49d583811887'
down_revision: Union[str, Sequence[str], None] = '644fc5acdae4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


llm_extraction_status_enum = postgresql.ENUM(
    "NOT_REQUESTED",
    "QUEUED",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    name="llmextractionstatus",
    create_type=False,
)

candidate_type_enum = postgresql.ENUM(
    "COURSE_INFO",
    "ASSIGNMENT",
    "EXAM",
    "IMPORTANT_DATE",
    "GRADING_POLICY",
    name="candidatetype",
    create_type=False,
)

candidate_status_enum = postgresql.ENUM(
    "PENDING",
    "ACCEPTED",
    "REJECTED",
    name="candidatestatus",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    llm_extraction_status_enum.create(op.get_bind(), checkfirst=True)
    candidate_type_enum.create(op.get_bind(), checkfirst=True)
    candidate_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'documents',
        sa.Column(
            'llm_extraction_status',
            llm_extraction_status_enum,
            nullable=False,
            server_default='NOT_REQUESTED',
        ),
    )
    op.add_column(
        'documents',
        sa.Column('llm_extraction_error', sa.Text(), nullable=True),
    )

    op.create_table(
        'extraction_candidates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'document_id',
            sa.Integer(),
            sa.ForeignKey('documents.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('candidate_type', candidate_type_enum, nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column(
            'status',
            candidate_status_enum,
            nullable=False,
            server_default='PENDING',
        ),
        sa.Column(
            'created_task_id',
            sa.Integer(),
            sa.ForeignKey('tasks.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'reviewed_by',
            sa.Integer(),
            sa.ForeignKey('users.id'),
            nullable=True,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        op.f('ix_extraction_candidates_document_id'),
        'extraction_candidates',
        ['document_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_extraction_candidates_document_id'),
        table_name='extraction_candidates',
    )
    op.drop_table('extraction_candidates')

    op.drop_column('documents', 'llm_extraction_error')
    op.drop_column('documents', 'llm_extraction_status')

    candidate_status_enum.drop(op.get_bind(), checkfirst=True)
    candidate_type_enum.drop(op.get_bind(), checkfirst=True)
    llm_extraction_status_enum.drop(op.get_bind(), checkfirst=True)
