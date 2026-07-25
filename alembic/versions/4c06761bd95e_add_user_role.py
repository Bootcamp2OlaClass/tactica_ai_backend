"""add user role

Revision ID: 4c06761bd95e
Revises: 17a40adcc6ad
Create Date: 2026-07-21 16:25:20.281861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c06761bd95e'
down_revision: Union[str, Sequence[str], None] = '17a40adcc6ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql


user_role_enum = postgresql.ENUM(
    "STUDENT",
    "ADMIN",
    name="userrole",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    user_role_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column(
            "role",
            user_role_enum,
            nullable=False,
            server_default="STUDENT",
        ),
    )

    op.alter_column(
        "users",
        "role",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "role")
    user_role_enum.drop(op.get_bind(), checkfirst=True)