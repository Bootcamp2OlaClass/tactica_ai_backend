"""add notification preference and log tables

Revision ID: bf77af1169fd
Revises: e6c70e70514b
Create Date: 2026-08-13 13:32:40.382401

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bf77af1169fd'
down_revision: Union[str, Sequence[str], None] = 'e6c70e70514b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


notification_type_enum = postgresql.ENUM(
    "ASSIGNMENT_DUE",
    "EXAM_COUNTDOWN",
    "WEEKLY_PLAN",
    "OVERDUE_TASK",
    "RECOVERY_PLAN",
    name="notificationtype",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    notification_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('notification_type', notification_type_enum, nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.UniqueConstraint(
            'user_id', 'notification_type', name='uq_notification_pref_user_type'
        ),
    )
    op.create_index(
        op.f('ix_notification_preferences_user_id'), 'notification_preferences', ['user_id']
    )

    op.create_table(
        'notification_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('notification_type', notification_type_enum, nullable=False),
        sa.Column('reference_id', sa.String(length=64), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column(
            'sent_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            'user_id', 'notification_type', 'reference_id', name='uq_notification_log_dedup'
        ),
    )
    op.create_index(op.f('ix_notification_logs_user_id'), 'notification_logs', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_notification_logs_user_id'), table_name='notification_logs')
    op.drop_table('notification_logs')

    op.drop_index(
        op.f('ix_notification_preferences_user_id'), table_name='notification_preferences'
    )
    op.drop_table('notification_preferences')

    notification_type_enum.drop(op.get_bind(), checkfirst=True)
