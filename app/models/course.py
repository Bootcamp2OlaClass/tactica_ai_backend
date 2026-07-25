from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.semester import Semester
    from app.models.task import Task


class CourseStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DROPPED = "dropped"
    ARCHIVED = "archived"


class Course(Base):
    __tablename__ = "courses"

    __table_args__ = (
        CheckConstraint(
            "credits >= 0 AND credits <= 20",
            name="ck_courses_credits_range",
        ),
        Index(
            "ix_courses_semester_id",
            "semester_id",
        ),
        Index(
            "ix_courses_status",
            "status",
        ),
        Index(
            "uq_courses_active_semester_code",
            "semester_id",
            "course_code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    semester_id: Mapped[int] = mapped_column(
        ForeignKey(
            "semesters.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    course_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    instructor_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    credits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    classroom: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    color: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[CourseStatus] = mapped_column(
        SQLEnum(CourseStatus),
        nullable=False,
        default=CourseStatus.ACTIVE,
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

    semester: Mapped["Semester"] = relationship(
        back_populates="courses",
    )

    tasks: Mapped[list["Task"]] = relationship(
        back_populates="course",
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="course",
    )