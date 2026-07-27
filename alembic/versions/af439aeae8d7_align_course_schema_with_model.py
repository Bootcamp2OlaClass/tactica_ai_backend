
"""align course schema with model

Revision ID: af439aeae8d7
Revises: 4520a6b51a7d
Create Date: 2026-07-26 04:31:22.975666
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision: str = "af439aeae8d7"
down_revision: Union[str, Sequence[str], None] = "4520a6b51a7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""

    # Create semesters table
    op.create_table(
        "semesters",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "academic_year",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "start_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "end_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "UPCOMING",
                "ACTIVE",
                "COMPLETED",
                "ARCHIVED",
                name="semesterstatus",
            ),
            server_default="UPCOMING",
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="semesters_user_id_fkey",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="semesters_pkey",
        ),
    )

    # Unique active semester name per user and academic year
    op.create_index(
        "uq_semesters_active_user_name_year",
        "semesters",
        ["user_id", "name", "academic_year"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'ACTIVE' AND is_deleted = false"
        ),
    )

    # Create PostgreSQL course status enum

    course_status_enum = sa.Enum(
        "ACTIVE",
        "COMPLETED",
        "DROPPED",
        "ARCHIVED",
        name="coursestatus",
    )

    course_status_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    # Add new columns to courses

    op.add_column(
        "courses",
        sa.Column(
            "semester_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "course_code",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "instructor_name",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "credits",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "classroom",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "color",
            sa.String(length=7),
            nullable=True,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "status",
            course_status_enum,
            server_default="ACTIVE",
            nullable=False,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Remove legacy development data

    op.execute("DELETE FROM tasks")
    op.execute("DELETE FROM documents")
    op.execute("DELETE FROM courses")

    # Make required course columns NOT NULL

    op.alter_column(
        "courses",
        "semester_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.alter_column(
        "courses",
        "course_code",
        existing_type=sa.String(length=50),
        nullable=False,
    )

    op.alter_column(
        "courses",
        "name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.alter_column(
        "courses",
        "credits",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # Create foreign key

    op.create_foreign_key(
        "courses_semester_id_fkey",
        "courses",
        "semesters",
        ["semester_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Create indexes

    op.create_index(
        "idx_courses_semester_id",
        "courses",
        ["semester_id"],
        unique=False,
    )

    op.create_index(
        "ix_courses_user_id",
        "courses",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "uq_active_course_code_per_semester",
        "courses",
        ["semester_id", "course_code"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    # Create check constraints

    op.create_check_constraint(
        "check_course_credits_positive",
        "courses",
        "credits > 0",
    )

    op.create_check_constraint(
        "check_hex_color",
        "courses",
        "color IS NULL OR color ~ '^#[0-9A-Fa-f]{6}$'",
    )

    # Remove old course columns

    op.drop_column(
        "courses",
        "professor",
    )

    op.drop_column(
        "courses",
        "title",
    )

    op.drop_column(
        "courses",
        "semester",
    )


def downgrade() -> None:
    """Downgrade database schema."""

    # Restore old course columns as nullable first

    op.add_column(
        "courses",
        sa.Column(
            "semester",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "courses",
        sa.Column(
            "professor",
            sa.String(length=255),
            nullable=True,
        ),
    )

    # Move data back to old columns

    op.execute(
        """
        UPDATE courses
        SET
            title = name,
            professor = instructor_name,
            semester = 'Unknown'
        """
    )

    # Restore required old columns
    op.alter_column(
        "courses",
        "title",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.alter_column(
        "courses",
        "semester",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    # Drop check constraints

    op.drop_constraint(
        "check_course_credits_positive",
        "courses",
        type_="check",
    )

    op.drop_constraint(
        "check_hex_color",
        "courses",
        type_="check",
    )

    # Drop foreign key
    op.drop_constraint(
        "courses_semester_id_fkey",
        "courses",
        type_="foreignkey",
    )

    # Drop indexes
    op.drop_index(
        "uq_active_course_code_per_semester",
        table_name="courses",
    )

    op.drop_index(
        "ix_courses_user_id",
        table_name="courses",
    )

    op.drop_index(
        "idx_courses_semester_id",
        table_name="courses",
    )

    # Drop new course columns
    op.drop_column(
        "courses",
        "updated_at",
    )

    op.drop_column(
        "courses",
        "is_deleted",
    )

    op.drop_column(
        "courses",
        "status",
    )

    op.drop_column(
        "courses",
        "description",
    )

    op.drop_column(
        "courses",
        "color",
    )

    op.drop_column(
        "courses",
        "classroom",
    )

    op.drop_column(
        "courses",
        "credits",
    )

    op.drop_column(
        "courses",
        "instructor_name",
    )

    op.drop_column(
        "courses",
        "name",
    )

    op.drop_column(
        "courses",
        "course_code",
    )

    op.drop_column(
        "courses",
        "semester_id",
    )

    # Drop semesters index and table
    
    op.drop_index(
        "uq_semesters_active_user_name_year",
        table_name="semesters",
    )

    op.drop_table(
        "semesters",
    )

    # Remove PostgreSQL enum types
    op.execute(
        "DROP TYPE IF EXISTS coursestatus"
    )

    op.execute(
        "DROP TYPE IF EXISTS semesterstatus"
    )