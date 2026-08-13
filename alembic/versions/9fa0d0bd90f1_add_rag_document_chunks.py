"""add rag document_chunks table

Revision ID: 9fa0d0bd90f1
Revises: 49d583811887
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9fa0d0bd90f1'
down_revision: Union[str, Sequence[str], None] = '49d583811887'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


chunk_embedding_status_enum = postgresql.ENUM(
    "NOT_REQUESTED",
    "QUEUED",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    name="chunkembeddingstatus",
    create_type=False,
)

# ADR-007: 768 dimensions, chosen so both supported embedding providers
# (Gemini gemini-embedding-001, OpenAI text-embedding-3-small) can produce
# it natively via an explicit request parameter.
EMBEDDING_DIMENSION = 768


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    chunk_embedding_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'documents',
        sa.Column(
            'chunk_embedding_status',
            chunk_embedding_status_enum,
            nullable=False,
            server_default='NOT_REQUESTED',
        ),
    )
    op.add_column(
        'documents',
        sa.Column('chunk_embedding_error', sa.Text(), nullable=True),
    )

    op.create_table(
        'document_chunks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'document_id',
            sa.Integer(),
            sa.ForeignKey('documents.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'course_id',
            sa.Integer(),
            sa.ForeignKey('courses.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='RESTRICT'),
            nullable=False,
        ),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('start_page', sa.Integer(), nullable=False),
        sa.Column('end_page', sa.Integer(), nullable=False),
        sa.Column('embedding', Vector(EMBEDDING_DIMENSION), nullable=True),
        sa.Column('embedding_model', sa.String(length=100), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # No vector index (IVFFlat/HNSW) per ADR-008 -- deliberately deferred
    # until real usage data justifies one. These plain B-tree indexes exist
    # purely to keep the mandatory tenant/course/document filters fast
    # regardless of the (absent) vector index.
    op.create_index(
        op.f('ix_document_chunks_document_id'),
        'document_chunks',
        ['document_id'],
    )
    op.create_index(
        op.f('ix_document_chunks_course_id'),
        'document_chunks',
        ['course_id'],
    )
    op.create_index(
        op.f('ix_document_chunks_user_id'),
        'document_chunks',
        ['user_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_document_chunks_user_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_course_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_document_id'), table_name='document_chunks')
    op.drop_table('document_chunks')

    op.drop_column('documents', 'chunk_embedding_error')
    op.drop_column('documents', 'chunk_embedding_status')

    chunk_embedding_status_enum.drop(op.get_bind(), checkfirst=True)

    # Deliberately does not DROP EXTENSION vector -- other tables/future
    # migrations may depend on it, and dropping a shared extension from a
    # single feature's downgrade is exactly the kind of blast-radius
    # mistake this project's migration discipline exists to avoid.
