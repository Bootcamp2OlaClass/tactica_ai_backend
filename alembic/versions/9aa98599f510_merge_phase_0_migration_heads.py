"""merge phase-0 migration heads

Revision ID: 9aa98599f510
Revises: 3ff95bb7faac, 58ee11f4781f, a293ea1c1e04
Create Date: 2026-08-12 13:18:25.255623

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9aa98599f510'
down_revision: Union[str, Sequence[str], None] = ('3ff95bb7faac', '58ee11f4781f', 'a293ea1c1e04')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
