from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.task import Task
    from app.models.user import User


class DocumentType(str, Enum):
    SYLLABUS = "SYLLABUS"
    LECTURE_NOTE = "LECTURE_NOTE"
    ASSIGNMENT = "ASSIGNMENT"
    SLIDE = "SLIDE"
    REFERENCE = "REFERENCE"
    OTHER = "OTHER"


class ProcessingStatus(str, Enum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExtractionMethod(str, Enum):
    NATIVE = "NATIVE"
    OCR = "OCR"  # reserved for when OCR is actually implemented — see Phase 05 notes
    UNSUPPORTED = "UNSUPPORTED"  # OCR would be required but isn't available yet


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    course_id: Mapped[int] = mapped_column(
        ForeignKey(
            "courses.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    original_file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    stored_file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
    )

    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    document_type: Mapped[DocumentType] = mapped_column(
        SQLEnum(
            DocumentType,
            name="documenttype",
        ),
        nullable=False,
        default=DocumentType.OTHER,
        server_default=DocumentType.OTHER.value,
    )

    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SQLEnum(
            ProcessingStatus,
            name="processingstatus",
        ),
        nullable=False,
        default=ProcessingStatus.UPLOADED,
        server_default=ProcessingStatus.UPLOADED.value,
    )

    processing_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    extraction_method: Mapped[ExtractionMethod | None] = mapped_column(
        SQLEnum(
            ExtractionMethod,
            name="extractionmethod",
        ),
        nullable=True,
        default=None,
    )

    page_count: Mapped[int | None] = mapped_column(
        nullable=True,
        default=None,
    )

    text_length: Mapped[int | None] = mapped_column(
        nullable=True,
        default=None,
    )

    extracted_content_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        default=None,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    course: Mapped["Course"] = relationship(
        back_populates="documents",
    )

    uploader: Mapped["User"] = relationship(
        back_populates="documents",
        foreign_keys=[uploaded_by],
    )

    source_tasks: Mapped[list["Task"]] = relationship(
        back_populates="source_document",
    )