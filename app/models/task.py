from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.document import Document


class TaskType(str, Enum):
    ASSIGNMENT = "assignment"
    EXAM = "exam"
    QUIZ = "quiz"
    READING = "reading"
    PROJECT = "project"
    PRESENTATION = "presentation"
    OTHER = "other"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskSource(str, Enum):
    MANUAL = "manual"
    DOCUMENT_EXTRACTION = "document_extraction"
    AI_GENERATED = "ai_generated"


class Task(Base):
    __tablename__ = "tasks"

    __table_args__ = (
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes >= 0",
            name="ck_tasks_estimated_minutes_nonnegative",
        ),
        Index("ix_tasks_course_id", "course_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_due_at", "due_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"),
        nullable=False,
    )

    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        default=None,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    task_type: Mapped[TaskType] = mapped_column(
        SQLEnum(
            TaskType,
            name="tasktype",
        ),
        nullable=False,
        default=TaskType.OTHER,
    )

    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(
            TaskStatus,
            name="taskstatus",
        ),
        nullable=False,
        default=TaskStatus.TODO,
    )

    priority: Mapped[TaskPriority] = mapped_column(
        SQLEnum(
            TaskPriority,
            name="taskpriority",
        ),
        nullable=False,
        default=TaskPriority.MEDIUM,
    )

    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    estimated_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    source: Mapped[TaskSource] = mapped_column(
        SQLEnum(
            TaskSource,
            name="tasksource",
        ),
        nullable=False,
        default=TaskSource.MANUAL,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
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
        back_populates="tasks",
    )

    source_document: Mapped["Document | None"] = relationship(
        back_populates="source_tasks",

    )

    @property
    def is_overdue(self) -> bool:
        if self.due_at is None:
            return False

        if self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        }:
            return False

        return self.due_at < datetime.now(timezone.utc)