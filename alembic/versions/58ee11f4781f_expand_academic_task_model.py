"""expand academic task model

Revision ID: 58ee11f4781f
Revises: 4c06761bd95e
Create Date: 2026-07-25 19:26:49.224867
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Revision identifiers, used by Alembic.
revision: str = "58ee11f4781f"
down_revision: Union[str, Sequence[str], None] = "4c06761bd95e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expand the tasks table for academic task management."""

    connection = op.get_bind()

    # Create the new PostgreSQL enum types before using them in columns.
    task_type_enum = postgresql.ENUM(
        "ASSIGNMENT",
        "EXAM",
        "QUIZ",
        "READING",
        "PROJECT",
        "PRESENTATION",
        "OTHER",
        name="tasktype",
    )
    task_priority_enum = postgresql.ENUM(
        "LOW",
        "MEDIUM",
        "HIGH",
        "URGENT",
        name="taskpriority",
    )
    task_source_enum = postgresql.ENUM(
        "MANUAL",
        "DOCUMENT_EXTRACTION",
        "AI_GENERATED",
        name="tasksource",
    )

    task_type_enum.create(connection, checkfirst=True)
    task_priority_enum.create(connection, checkfirst=True)
    task_source_enum.create(connection, checkfirst=True)

    # Replace the old taskstatus enum.
    #
    # Old:
    # TODO, IN_PROGRESS, COMPLETED, OVERDUE
    #
    # New:
    # TODO, IN_PROGRESS, COMPLETED, CANCELLED
    #
    # Existing OVERDUE records become TODO because overdue is now derived
    # from due_at and the current time.
    op.execute(
        "ALTER TABLE tasks ALTER COLUMN status DROP DEFAULT"
    )
    op.execute(
        "ALTER TYPE taskstatus RENAME TO taskstatus_old"
    )
    op.execute(
        """
        CREATE TYPE taskstatus AS ENUM (
            'TODO',
            'IN_PROGRESS',
            'COMPLETED',
            'CANCELLED'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE tasks
        ALTER COLUMN status TYPE taskstatus
        USING (
            CASE
                WHEN status::text = 'OVERDUE' THEN 'TODO'
                ELSE status::text
            END
        )::taskstatus
        """
    )
    op.execute("DROP TYPE taskstatus_old")

    # Rename the existing deadline column instead of dropping it.
    # This preserves all current deadline values.
    op.alter_column(
        "tasks",
        "due_date",
        new_column_name="due_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )

    # Optional columns can be added directly because existing rows may use NULL.
    op.add_column(
        "tasks",
        sa.Column(
            "source_document_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "estimated_minutes",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Required columns need temporary server defaults so existing rows receive
    # valid values during the migration.
    op.add_column(
        "tasks",
        sa.Column(
            "task_type",
            postgresql.ENUM(
                "ASSIGNMENT",
                "EXAM",
                "QUIZ",
                "READING",
                "PROJECT",
                "PRESENTATION",
                "OTHER",
                name="tasktype",
                create_type=False,
            ),
            nullable=False,
            server_default="OTHER",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "priority",
            postgresql.ENUM(
                "LOW",
                "MEDIUM",
                "HIGH",
                "URGENT",
                name="taskpriority",
                create_type=False,
            ),
            nullable=False,
            server_default="MEDIUM",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "source",
            postgresql.ENUM(
                "MANUAL",
                "DOCUMENT_EXTRACTION",
                "AI_GENERATED",
                name="tasksource",
                create_type=False,
            ),
            nullable=False,
            server_default="MANUAL",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Remove temporary defaults. Future defaults are handled by SQLAlchemy.
    op.alter_column(
        "tasks",
        "task_type",
        server_default=None,
    )
    op.alter_column(
        "tasks",
        "priority",
        server_default=None,
    )
    op.alter_column(
        "tasks",
        "source",
        server_default=None,
    )
    op.alter_column(
        "tasks",
        "is_deleted",
        server_default=None,
    )

    # Prevent negative task-duration estimates.
    op.create_check_constraint(
        "ck_tasks_estimated_minutes_nonnegative",
        "tasks",
        "estimated_minutes IS NULL OR estimated_minutes >= 0",
    )

    # Add the optional relationship to the source document.
    op.create_foreign_key(
        "fk_tasks_source_document_id_documents",
        "tasks",
        "documents",
        ["source_document_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add indexes required for common task and deadline queries.
    op.create_index(
        "ix_tasks_course_id",
        "tasks",
        ["course_id"],
        unique=False,
    )
    op.create_index(
        "ix_tasks_status",
        "tasks",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_tasks_due_at",
        "tasks",
        ["due_at"],
        unique=False,
    )


def downgrade() -> None:
    """Restore the original tasks table structure."""

    # Remove objects that depend on the new columns first.
    op.drop_index(
        "ix_tasks_due_at",
        table_name="tasks",
    )
    op.drop_index(
        "ix_tasks_status",
        table_name="tasks",
    )
    op.drop_index(
        "ix_tasks_course_id",
        table_name="tasks",
    )

    op.drop_constraint(
        "fk_tasks_source_document_id_documents",
        "tasks",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_tasks_estimated_minutes_nonnegative",
        "tasks",
        type_="check",
    )

    # Rename the deadline column back while preserving its data.
    op.alter_column(
        "tasks",
        "due_at",
        new_column_name="due_date",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )

    # Remove the newly added columns.
    op.drop_column("tasks", "updated_at")
    op.drop_column("tasks", "is_deleted")
    op.drop_column("tasks", "source")
    op.drop_column("tasks", "completed_at")
    op.drop_column("tasks", "estimated_minutes")
    op.drop_column("tasks", "priority")
    op.drop_column("tasks", "task_type")
    op.drop_column("tasks", "description")
    op.drop_column("tasks", "source_document_id")

    # Restore the original taskstatus enum.
    #
    # CANCELLED did not exist in the previous schema, so cancelled records
    # become TODO during downgrade.
    op.execute(
        "ALTER TABLE tasks ALTER COLUMN status DROP DEFAULT"
    )
    op.execute(
        "ALTER TYPE taskstatus RENAME TO taskstatus_new"
    )
    op.execute(
        """
        CREATE TYPE taskstatus AS ENUM (
            'TODO',
            'IN_PROGRESS',
            'COMPLETED',
            'OVERDUE'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE tasks
        ALTER COLUMN status TYPE taskstatus
        USING (
            CASE
                WHEN status::text = 'CANCELLED' THEN 'TODO'
                ELSE status::text
            END
        )::taskstatus
        """
    )
    op.execute("DROP TYPE taskstatus_new")

    # Remove enum types that are no longer used.
    postgresql.ENUM(
        name="tasksource",
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )
    postgresql.ENUM(
        name="taskpriority",
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )
    postgresql.ENUM(
        name="tasktype",
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )