"""merge migration heads

Revision ID: 4520a6b51a7d
Revises: 3b4e98b64361, 4c06761bd95e
Create Date: 2026-07-25 21:39:31.949604

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4520a6b51a7d'
down_revision: Union[str, Sequence[str], None] = ('3b4e98b64361', '4c06761bd95e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
