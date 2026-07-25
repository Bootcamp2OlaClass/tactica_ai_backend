from enum import Enum
from datetime import datetime, date
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func, Boolean, Enum as SQLEnum, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.user import User

class SemesterStatus(str, Enum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class Semester(Base):
    __tablename__ = "semesters"
    
    __table_args__ = (
        Index(
            "uq_semesters_active_user_name_year",
            "user_id",
            "name",
            "academic_year",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )
    
    id: Mapped[int] = mapped_column(
        primary_key=True
    )
    
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )
    
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    academic_year: Mapped[int] = mapped_column(
        nullable=False
    )
    
    start_date: Mapped[date] = mapped_column(
        nullable=False
    )
    
    end_date: Mapped[date] = mapped_column(
        nullable = False
    )
    
    status: Mapped[SemesterStatus] = mapped_column(
        SQLEnum(SemesterStatus),
        nullable=False,
        default=SemesterStatus.UPCOMING,
    )
    
    description: Mapped[str|None] = mapped_column(
        String(255),
        nullable=True
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None
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
        nullable = False
    )
    
    user: Mapped["User"] = relationship(
        back_populates="semesters"
    )
    
    courses: Mapped[list["Course"]] = relationship(
        back_populates="semester"
    )
    
