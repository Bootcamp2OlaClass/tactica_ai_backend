"""add answer_mode to messages

Revision ID: c1a9d0e2f3b4
Revises: bf77af1169fd
Create Date: 2026-08-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c1a9d0e2f3b4'
down_revision: Union[str, Sequence[str], None] = 'bf77af1169fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


answer_mode_enum = postgresql.ENUM(
    "GENERAL",
    "GROUNDED",
    "MISSING_PERSONAL_CONTEXT",
    name="answermode",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    answer_mode_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'messages',
        sa.Column('answer_mode', answer_mode_enum, nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('messages', 'answer_mode')
    answer_mode_enum.drop(op.get_bind(), checkfirst=True)
