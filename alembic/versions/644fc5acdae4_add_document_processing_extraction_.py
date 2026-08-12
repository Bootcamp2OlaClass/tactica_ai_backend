"""add document processing extraction fields

Revision ID: 644fc5acdae4
Revises: 25e18d29e845
Create Date: 2026-08-12 20:27:04.394454

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '644fc5acdae4'
down_revision: Union[str, Sequence[str], None] = '25e18d29e845'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


extraction_method_enum = postgresql.ENUM(
    "NATIVE",
    "OCR",
    "UNSUPPORTED",
    name="extractionmethod",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    extraction_method_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('documents', sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('extraction_method', extraction_method_enum, nullable=True))
    op.add_column('documents', sa.Column('page_count', sa.Integer(), nullable=True))
    op.add_column('documents', sa.Column('text_length', sa.Integer(), nullable=True))
    op.add_column('documents', sa.Column('extracted_content_path', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'extracted_content_path')
    op.drop_column('documents', 'text_length')
    op.drop_column('documents', 'page_count')
    op.drop_column('documents', 'extraction_method')
    op.drop_column('documents', 'processed_at')

    extraction_method_enum.drop(op.get_bind(), checkfirst=True)
