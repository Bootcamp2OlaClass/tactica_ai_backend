from datetime import datetime
from typing import TYPE_CHECKING
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text, Boolean, func, CheckConstraint, Index, text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.semester import Semester
    from app.models.task import Task
    from app.models.user import User

class CourseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    DROPPED = "DROPPED"
    ARCHIVED = "ARCHIVED"

class Course(Base):
    __tablename__ = "courses"

    __table_args__ = (
        CheckConstraint(
            "credits > 0",
            name="check_course_credits_positive"
        ),

        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9A-Fa-f]{6}$'",
            name="check_hex_color"
        ),

        Index(
            "idx_courses_semester_id",
            "semester_id",
        ),

        Index(
            "uq_active_course_code_per_semester",
            "semester_id",
            "course_code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
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
        nullable=False,
    )

    classroom: Mapped[str | None] = mapped_column(
        String(100),
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
        SQLEnum(
            CourseStatus,
            name="coursestatus",
        ),
        nullable=False,
        default=CourseStatus.ACTIVE,
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
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

# Relationships
    user: Mapped["User"] = relationship(
        back_populates="courses",
    )

    semester: Mapped["Semester"] = relationship(
        back_populates="courses",
    )

    tasks: Mapped[list["Task"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )
   
    