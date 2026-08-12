from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.task import Task
    from app.models.user import User


class CandidateType(str, Enum):
    COURSE_INFO = "COURSE_INFO"
    ASSIGNMENT = "ASSIGNMENT"
    EXAM = "EXAM"
    IMPORTANT_DATE = "IMPORTANT_DATE"
    GRADING_POLICY = "GRADING_POLICY"


class CandidateStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class ExtractionCandidate(Base):
    """A single LLM-extracted fact awaiting student review — see ADR-006.
    Never auto-committed as a real Task/Course change; `payload` mirrors the
    matching app.schemas.extraction.Extracted* shape for `candidate_type`.
    """

    __tablename__ = "extraction_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    candidate_type: Mapped[CandidateType] = mapped_column(
        SQLEnum(CandidateType, name="candidatetype"),
        nullable=False,
    )

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    source_page: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )

    status: Mapped[CandidateStatus] = mapped_column(
        SQLEnum(CandidateStatus, name="candidatestatus"),
        nullable=False,
        default=CandidateStatus.PENDING,
        server_default=CandidateStatus.PENDING.value,
    )

    created_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        default=None,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(
        back_populates="extraction_candidates",
    )

    created_task: Mapped["Task | None"] = relationship()

    reviewer: Mapped["User | None"] = relationship()
