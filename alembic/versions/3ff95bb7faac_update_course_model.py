"""update course model

Revision ID: 3ff95bb7faac
Revises: 1bb036026f36
Create Date: 2026-07-25 23:48:54.004615
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision: str = "3ff95bb7faac"
down_revision: Union[str, Sequence[str], None] = "1bb036026f36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

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

    # Create the semesters table because the current migration history
    # does not yet create it.
    op.create_table(
        "semesters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("academic_year", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "UPCOMING",
                "ACTIVE",
                "COMPLETED",
                "ARCHIVED",
                name="semesterstatus",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=255), nullable=True),
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
            name="fk_semesters_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "uq_semesters_active_user_name_year",
        "semesters",
        ["user_id", "name", "academic_year"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # Add the new course fields.
    op.add_column(
        "courses",
        sa.Column("semester_id", sa.Integer(), nullable=False),
    )
    op.add_column(
        "courses",
        sa.Column("course_code", sa.String(length=50), nullable=False),
    )
    op.add_column(
        "courses",
        sa.Column("name", sa.String(length=255), nullable=False),
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
        sa.Column("credits", sa.Integer(), nullable=False),
    )
    op.add_column(
        "courses",
        sa.Column("classroom", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "courses",
        sa.Column("color", sa.String(length=7), nullable=True),
    )
    op.add_column(
        "courses",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "courses",
        sa.Column(
            "status",
            course_status_enum,
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

    # Validate the supported course credit range.
    op.create_check_constraint(
        "ck_courses_credits_range",
        "courses",
        "credits >= 0 AND credits <= 20",
    )

    # Add the relationship from courses to semesters.
    op.create_foreign_key(
        "fk_courses_semester_id_semesters",
        "courses",
        "semesters",
        ["semester_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Add indexes used by course queries.
    op.create_index(
        "ix_courses_semester_id",
        "courses",
        ["semester_id"],
        unique=False,
    )
    op.create_index(
        "ix_courses_status",
        "courses",
        ["status"],
        unique=False,
    )
    op.create_index(
        "uq_courses_active_semester_code",
        "courses",
        ["semester_id", "course_code"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    # Remove the old direct user ownership and old course fields.
    op.drop_constraint(
        "courses_user_id_fkey",
        "courses",
        type_="foreignkey",
    )
    op.drop_column("courses", "professor")
    op.drop_column("courses", "title")
    op.drop_column("courses", "user_id")
    op.drop_column("courses", "semester")
    
def downgrade() -> None:
    """Downgrade schema."""

    # Restore the old course fields.
    op.add_column(
        "courses",
        sa.Column(
            "semester",
            sa.String(length=255),
            nullable=False,
        ),
    )
    op.add_column(
        "courses",
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
    )
    op.add_column(
        "courses",
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
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

    op.create_foreign_key(
        "courses_user_id_fkey",
        "courses",
        "users",
        ["user_id"],
        ["id"],
    )

    # Remove new indexes and constraints.
    op.drop_index(
        "uq_courses_active_semester_code",
        table_name="courses",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_index(
        "ix_courses_status",
        table_name="courses",
    )
    op.drop_index(
        "ix_courses_semester_id",
        table_name="courses",
    )

    op.drop_constraint(
        "fk_courses_semester_id_semesters",
        "courses",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_courses_credits_range",
        "courses",
        type_="check",
    )

    # Remove the new course fields.
    op.drop_column("courses", "updated_at")
    op.drop_column("courses", "is_deleted")
    op.drop_column("courses", "status")
    op.drop_column("courses", "description")
    op.drop_column("courses", "color")
    op.drop_column("courses", "classroom")
    op.drop_column("courses", "credits")
    op.drop_column("courses", "instructor_name")
    op.drop_column("courses", "name")
    op.drop_column("courses", "course_code")
    op.drop_column("courses", "semester_id")

    # Remove the semesters table.
    op.drop_index(
        "uq_semesters_active_user_name_year",
        table_name="semesters",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_table("semesters")

    # PostgreSQL enum types remain after their columns are removed,
    # so remove them explicitly.
    sa.Enum(name="coursestatus").drop(
        op.get_bind(),
        checkfirst=True,
    )
    sa.Enum(name="semesterstatus").drop(
        op.get_bind(),
        checkfirst=True,
    )