"""Degree advisor models — see PHASE_11_DEGREE_ADVISOR.md.

**No real course catalog data ships with this codebase or any migration
here.** These tables define the architecture the phase brief calls for
(`DegreeProgram`, `CourseCatalogEntry`, `Prerequisite`, `DegreeRequirement`,
`StudentDegreeProgress`) so the validation pipeline
(app/services/degree_recommendation.py) has something real to validate
against once an institution's actual catalog is sourced -- a data-
acquisition task explicitly out of engineering's control, not resolved by
this phase. Test fixtures use small synthetic course codes (e.g.
"TEST101"), the same convention every other phase's tests already use for
course/task data -- never presented as, or seeded as, a real institution's
catalog.

`CourseCatalogEntry`/`Prerequisite`/`DegreeRequirement`/`DegreeProgram` are
shared reference data, not user-owned (per the phase's own Security
note) -- only `StudentDegreeProgress` has a `user_id`.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class CourseCatalogEntry(Base):
    __tablename__ = "course_catalog_entries"

    __table_args__ = (
        UniqueConstraint(
            "institution_name", "course_code", name="uq_catalog_institution_course_code"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    course_code: Mapped[str] = mapped_column(String(20), nullable=False)
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)

    # Which DegreeRequirement.category this course counts toward for a
    # credit-minimum requirement (e.g. "CS_ELECTIVE") -- nullable since not
    # every catalog entry counts toward any category-based requirement.
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Prerequisite(Base):
    """`course_id` requires `required_course_id` -- both real
    `CourseCatalogEntry` rows within the same institution; enforced at
    the application layer (app/services/degree_recommendation.py), not a
    DB constraint, since cross-institution mixing is a data-integrity
    concern the validation pipeline already checks explicitly."""

    __tablename__ = "prerequisites"

    __table_args__ = (
        UniqueConstraint("course_id", "required_course_id", name="uq_prerequisite_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("course_catalog_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    required_course_id: Mapped[int] = mapped_column(
        ForeignKey("course_catalog_entries.id", ondelete="CASCADE"), nullable=False
    )


class DegreeProgram(Base):
    __tablename__ = "degree_programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    catalog_year: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    requirements: Mapped[list["DegreeRequirement"]] = relationship(back_populates="degree_program")


class DegreeRequirement(Base):
    """Two requirement shapes, distinguished by which nullable field is
    set (enforced in app/services/degree_recommendation.py, not a DB
    constraint): a specific-course requirement (`required_course_id` set)
    or a category credit-minimum (`category` + `min_credits` set, e.g.
    "12 credits of CS electives")."""

    __tablename__ = "degree_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    degree_program_id: Mapped[int] = mapped_column(
        ForeignKey("degree_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    required_course_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_catalog_entries.id", ondelete="SET NULL"), nullable=True, default=None
    )
    min_credits: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    degree_program: Mapped["DegreeProgram"] = relationship(back_populates="requirements")


class StudentDegreeProgress(Base):
    """The one user-owned entity in this phase -- which degree program a
    student has declared. Completed-course matching against the catalog
    is done by `course_code` string match against the student's own
    (pre-existing) `Course` rows, not a new FK on that heavily-shared
    table -- see app/services/degree_recommendation.py."""

    __tablename__ = "student_degree_progress"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_student_degree_progress_one_per_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    degree_program_id: Mapped[int] = mapped_column(
        ForeignKey("degree_programs.id", ondelete="CASCADE"), nullable=False
    )
    declared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship()
    degree_program: Mapped["DegreeProgram"] = relationship()
