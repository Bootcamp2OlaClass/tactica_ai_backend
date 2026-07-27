from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING 

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.semester import Semester


class UserRole(str, PyEnum):
    STUDENT = "STUDENT"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="userrole",
        ),
        nullable=False,
        default=UserRole.STUDENT,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    courses: Mapped[list["Course"]] = relationship(
        back_populates="user",
    )

    semesters: Mapped[list["Semester"]] = relationship(
        back_populates="user",
    )