"""update course model

Revision ID: 3ff95bb7faac
Revises: 1bb036026f36
Create Date: 2026-07-25 23:48:54.004615
"""

from typing import Sequence, Union


revision: str = "3ff95bb7faac"
down_revision: Union[str, Sequence[str], None] = "1bb036026f36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Superseded by af439aeae8d7."""
    pass


def downgrade() -> None:
    """No-op because this revision applies no schema changes."""
    pass