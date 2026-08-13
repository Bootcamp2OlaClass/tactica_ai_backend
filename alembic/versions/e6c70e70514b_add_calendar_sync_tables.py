"""add calendar sync tables

Revision ID: e6c70e70514b
Revises: 762e75066126
Create Date: 2026-08-13 13:12:58.087879

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e6c70e70514b'
down_revision: Union[str, Sequence[str], None] = '762e75066126'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


calendar_sync_status_enum = postgresql.ENUM(
    "SYNCED",
    "FAILED",
    name="calendarsyncstatus",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    calendar_sync_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'calendar_connections',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=False),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'connected_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint('user_id', name='uq_calendar_connection_one_per_user'),
    )
    op.create_index(
        op.f('ix_calendar_connections_user_id'), 'calendar_connections', ['user_id']
    )

    op.create_table(
        'calendar_syncs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'task_id',
            sa.Integer(),
            sa.ForeignKey('tasks.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('provider_event_id', sa.String(length=255), nullable=True),
        sa.Column('sync_status', calendar_sync_status_enum, nullable=False),
        sa.Column('sync_error', sa.Text(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('task_id', name='uq_calendar_sync_one_per_task'),
    )
    op.create_index(op.f('ix_calendar_syncs_task_id'), 'calendar_syncs', ['task_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_calendar_syncs_task_id'), table_name='calendar_syncs')
    op.drop_table('calendar_syncs')

    op.drop_index(op.f('ix_calendar_connections_user_id'), table_name='calendar_connections')
    op.drop_table('calendar_connections')

    calendar_sync_status_enum.drop(op.get_bind(), checkfirst=True)
