"""extend document model for academic files

Revision ID: a293ea1c1e04
Revises: af439aeae8d7
Create Date: 2026-07-31 03:38:54.438208
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a293ea1c1e04"
down_revision: Union[str, Sequence[str], None] = "af439aeae8d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


document_type_enum = postgresql.ENUM(
    "SYLLABUS",
    "LECTURE_NOTE",
    "ASSIGNMENT",
    "SLIDE",
    "REFERENCE",
    "OTHER",
    name="documenttype",
)

processing_status_enum = postgresql.ENUM(
    "UPLOADED",
    "QUEUED",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    name="processingstatus",
)

document_status_enum = postgresql.ENUM(
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    name="documentstatus",
)


def upgrade() -> None:
    """Extend documents while preserving existing file metadata."""

    bind = op.get_bind()

    document_type_enum.create(bind, checkfirst=True)
    processing_status_enum.create(bind, checkfirst=True)

    # Add required replacement fields as nullable first so existing rows
    # can be migrated before NOT NULL constraints are applied.
    op.add_column(
        "documents",
        sa.Column(
            "uploaded_by",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "original_file_name",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "stored_file_name",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "storage_path",
            sa.String(length=500),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "checksum",
            sa.String(length=64),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "document_type",
            document_type_enum,
            nullable=False,
            server_default="OTHER",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "processing_status",
            processing_status_enum,
            nullable=False,
            server_default="UPLOADED",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "processing_error",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Preserve old filename and storage metadata.
    op.execute(
        """
        UPDATE documents
        SET
            original_file_name = file_name,
            stored_file_name = file_name,
            storage_path = file_path
        """
    )

    # Resolve uploader through document -> course -> semester -> user.
    op.execute(
        """
        UPDATE documents AS d
        SET uploaded_by = s.user_id
        FROM courses AS c
        JOIN semesters AS s
            ON s.id = c.semester_id
        WHERE d.course_id = c.id
        """
    )

    # Convert the previous processing status to the new enum.
    op.execute(
        """
        UPDATE documents
        SET processing_status = (
            CASE status::text
                WHEN 'PENDING' THEN 'UPLOADED'
                WHEN 'PROCESSING' THEN 'PROCESSING'
                WHEN 'COMPLETED' THEN 'COMPLETED'
                WHEN 'FAILED' THEN 'FAILED'
                ELSE 'UPLOADED'
            END
        )::processingstatus
        """
    )

    # Existing rows have now been backfilled, so these columns can become
    # required to match the SQLAlchemy model.
    op.alter_column(
        "documents",
        "uploaded_by",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.alter_column(
        "documents",
        "original_file_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.alter_column(
        "documents",
        "stored_file_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.alter_column(
        "documents",
        "storage_path",
        existing_type=sa.String(length=500),
        nullable=False,
    )

    # Replace the old file_path uniqueness constraint with storage_path.
    op.drop_constraint(
        op.f("documents_file_path_key"),
        "documents",
        type_="unique",
    )

    op.create_index(
        op.f("ix_documents_checksum"),
        "documents",
        ["checksum"],
        unique=False,
    )

    op.create_index(
        op.f("ix_documents_uploaded_by"),
        "documents",
        ["uploaded_by"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_documents_storage_path",
        "documents",
        ["storage_path"],
    )

    op.create_foreign_key(
        "fk_documents_uploaded_by_users",
        "documents",
        "users",
        ["uploaded_by"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Remove replaced columns only after their data has been copied.
    op.drop_column("documents", "status")
    op.drop_column("documents", "file_path")
    op.drop_column("documents", "file_name")


def downgrade() -> None:
    """Restore the previous document schema while preserving metadata."""

    bind = op.get_bind()

    document_status_enum.create(bind, checkfirst=True)

    # Add previous columns as nullable first so current rows can be copied.
    op.add_column(
        "documents",
        sa.Column(
            "file_name",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "file_path",
            sa.String(length=500),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "status",
            document_status_enum,
            nullable=True,
        ),
    )

    # Restore values from the extended schema.
    op.execute(
        """
        UPDATE documents
        SET
            file_name = original_file_name,
            file_path = storage_path,
            status = (
                CASE processing_status::text
                    WHEN 'UPLOADED' THEN 'PENDING'
                    WHEN 'QUEUED' THEN 'PENDING'
                    WHEN 'PROCESSING' THEN 'PROCESSING'
                    WHEN 'COMPLETED' THEN 'COMPLETED'
                    WHEN 'FAILED' THEN 'FAILED'
                    ELSE 'PENDING'
                END
            )::documentstatus
        """
    )

    op.alter_column(
        "documents",
        "file_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.alter_column(
        "documents",
        "file_path",
        existing_type=sa.String(length=500),
        nullable=False,
    )

    op.alter_column(
        "documents",
        "status",
        existing_type=document_status_enum,
        nullable=False,
    )

    op.drop_constraint(
        "fk_documents_uploaded_by_users",
        "documents",
        type_="foreignkey",
    )

    op.drop_constraint(
        "uq_documents_storage_path",
        "documents",
        type_="unique",
    )

    op.drop_index(
        op.f("ix_documents_uploaded_by"),
        table_name="documents",
    )

    op.drop_index(
        op.f("ix_documents_checksum"),
        table_name="documents",
    )

    op.create_unique_constraint(
        op.f("documents_file_path_key"),
        "documents",
        ["file_path"],
    )

    op.drop_column("documents", "is_deleted")
    op.drop_column("documents", "processing_error")
    op.drop_column("documents", "processing_status")
    op.drop_column("documents", "document_type")
    op.drop_column("documents", "checksum")
    op.drop_column("documents", "storage_path")
    op.drop_column("documents", "stored_file_name")
    op.drop_column("documents", "original_file_name")
    op.drop_column("documents", "uploaded_by")

    processing_status_enum.drop(bind, checkfirst=True)
    document_type_enum.drop(bind, checkfirst=True)