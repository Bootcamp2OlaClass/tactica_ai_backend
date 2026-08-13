"""add degree advisor tables

Revision ID: 762e75066126
Revises: 87d2973cd5d7
Create Date: 2026-08-13 10:29:50.349779

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '762e75066126'
down_revision: Union[str, Sequence[str], None] = '87d2973cd5d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'course_catalog_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('institution_name', sa.String(length=200), nullable=False),
        sa.Column('course_code', sa.String(length=20), nullable=False),
        sa.Column('course_name', sa.String(length=255), nullable=False),
        sa.Column('credits', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            'institution_name', 'course_code', name='uq_catalog_institution_course_code'
        ),
    )
    op.create_index(
        op.f('ix_course_catalog_entries_institution_name'),
        'course_catalog_entries',
        ['institution_name'],
    )

    op.create_table(
        'degree_programs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('institution_name', sa.String(length=200), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('catalog_year', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        op.f('ix_degree_programs_institution_name'), 'degree_programs', ['institution_name']
    )

    op.create_table(
        'degree_requirements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'degree_program_id',
            sa.Integer(),
            sa.ForeignKey('degree_programs.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column(
            'required_course_id',
            sa.Integer(),
            sa.ForeignKey('course_catalog_entries.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('min_credits', sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f('ix_degree_requirements_degree_program_id'),
        'degree_requirements',
        ['degree_program_id'],
    )

    op.create_table(
        'prerequisites',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'course_id',
            sa.Integer(),
            sa.ForeignKey('course_catalog_entries.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'required_course_id',
            sa.Integer(),
            sa.ForeignKey('course_catalog_entries.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.UniqueConstraint('course_id', 'required_course_id', name='uq_prerequisite_pair'),
    )
    op.create_index(op.f('ix_prerequisites_course_id'), 'prerequisites', ['course_id'])

    op.create_table(
        'student_degree_progress',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'degree_program_id',
            sa.Integer(),
            sa.ForeignKey('degree_programs.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'declared_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint('user_id', name='uq_student_degree_progress_one_per_user'),
    )
    op.create_index(
        op.f('ix_student_degree_progress_user_id'), 'student_degree_progress', ['user_id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_student_degree_progress_user_id'), table_name='student_degree_progress'
    )
    op.drop_table('student_degree_progress')

    op.drop_index(op.f('ix_prerequisites_course_id'), table_name='prerequisites')
    op.drop_table('prerequisites')

    op.drop_index(
        op.f('ix_degree_requirements_degree_program_id'), table_name='degree_requirements'
    )
    op.drop_table('degree_requirements')

    op.drop_index(op.f('ix_degree_programs_institution_name'), table_name='degree_programs')
    op.drop_table('degree_programs')

    op.drop_index(
        op.f('ix_course_catalog_entries_institution_name'), table_name='course_catalog_entries'
    )
    op.drop_table('course_catalog_entries')
