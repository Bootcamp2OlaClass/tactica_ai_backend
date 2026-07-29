"""merge document metadata and user role heads

Revision ID: 1bb036026f36
Revises: 3b4e98b64361, 4c06761bd95e
Create Date: 2026-07-25 23:47:42.999715

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1bb036026f36'
down_revision: Union[str, Sequence[str], None] = ('3b4e98b64361', '4c06761bd95e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
