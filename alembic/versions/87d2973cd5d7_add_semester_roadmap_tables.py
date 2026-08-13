"""add semester roadmap tables

Revision ID: 87d2973cd5d7
Revises: 6d3c225d3c24
Create Date: 2026-08-13 09:53:29.848374

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '87d2973cd5d7'
down_revision: Union[str, Sequence[str], None] = '6d3c225d3c24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


roadmap_generation_status_enum = postgresql.ENUM(
    "NOT_REQUESTED",
    "QUEUED",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    name="roadmapgenerationstatus",
    create_type=False,
)

roadmap_item_type_enum = postgresql.ENUM(
    "MILESTONE",
    "ASSIGNMENT_PREPARATION",
    "EXAM_PREPARATION",
    "RECOMMENDATION",
    name="roadmapitemtype",
    create_type=False,
)

roadmap_item_origin_enum = postgresql.ENUM(
    "DETERMINISTIC",
    "AI_GENERATED",
    name="roadmapitemorigin",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    roadmap_generation_status_enum.create(op.get_bind(), checkfirst=True)
    roadmap_item_type_enum.create(op.get_bind(), checkfirst=True)
    roadmap_item_origin_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'semester_roadmaps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'semester_id',
            sa.Integer(),
            sa.ForeignKey('semesters.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'status',
            roadmap_generation_status_enum,
            nullable=False,
            server_default='NOT_REQUESTED',
        ),
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('generation_error', sa.Text(), nullable=True),
        sa.Column('recommendations_unavailable_reason', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        op.f('ix_semester_roadmaps_semester_id'),
        'semester_roadmaps',
        ['semester_id'],
        unique=True,
    )

    op.create_table(
        'roadmap_weeks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'roadmap_id',
            sa.Integer(),
            sa.ForeignKey('semester_roadmaps.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('week_number', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.UniqueConstraint('roadmap_id', 'week_number', name='uq_roadmap_week_number'),
    )
    op.create_index(
        op.f('ix_roadmap_weeks_roadmap_id'), 'roadmap_weeks', ['roadmap_id']
    )

    op.create_table(
        'roadmap_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'week_id',
            sa.Integer(),
            sa.ForeignKey('roadmap_weeks.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'roadmap_id',
            sa.Integer(),
            sa.ForeignKey('semester_roadmaps.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('item_type', roadmap_item_type_enum, nullable=False),
        sa.Column('origin', roadmap_item_origin_enum, nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'task_id',
            sa.Integer(),
            sa.ForeignKey('tasks.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'course_id',
            sa.Integer(),
            sa.ForeignKey('courses.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column(
            'is_user_edited', sa.Boolean(), nullable=False, server_default='false'
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        op.f('ix_roadmap_items_roadmap_id'), 'roadmap_items', ['roadmap_id']
    )
    op.create_index(op.f('ix_roadmap_items_task_id'), 'roadmap_items', ['task_id'])
    op.create_index(op.f('ix_roadmap_items_week_id'), 'roadmap_items', ['week_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_roadmap_items_week_id'), table_name='roadmap_items')
    op.drop_index(op.f('ix_roadmap_items_task_id'), table_name='roadmap_items')
    op.drop_index(op.f('ix_roadmap_items_roadmap_id'), table_name='roadmap_items')
    op.drop_table('roadmap_items')

    op.drop_index(op.f('ix_roadmap_weeks_roadmap_id'), table_name='roadmap_weeks')
    op.drop_table('roadmap_weeks')

    op.drop_index(
        op.f('ix_semester_roadmaps_semester_id'), table_name='semester_roadmaps'
    )
    op.drop_table('semester_roadmaps')

    roadmap_item_origin_enum.drop(op.get_bind(), checkfirst=True)
    roadmap_item_type_enum.drop(op.get_bind(), checkfirst=True)
    roadmap_generation_status_enum.drop(op.get_bind(), checkfirst=True)
