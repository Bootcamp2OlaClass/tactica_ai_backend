"""Semester roadmap models — see PHASE_09_SEMESTER_ROADMAP.md.

Three-level structure (SemesterRoadmap -> RoadmapWeek -> RoadmapItem)
matching the phase brief's target shape. Deliberately does NOT duplicate
Task data: a deterministic item (MILESTONE/ASSIGNMENT_PREP/EXAM_PREP)
references its source Task via `task_id` rather than copying its title;
`due_date` is the one exception, kept as a display/sort-only snapshot for
the same reason DocumentChunk denormalizes user_id/course_id (Phase 07,
ADR-003) -- cheap, justified, and never the source of truth.
"""

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.semester import Semester
    from app.models.task import Task


class RoadmapGenerationStatus(str, Enum):
    """Mirrors ChunkEmbeddingStatus's (Phase 07) shape exactly -- same
    naming convention reused deliberately, not reinvented per domain."""

    NOT_REQUESTED = "NOT_REQUESTED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RoadmapItemType(str, Enum):
    MILESTONE = "MILESTONE"
    ASSIGNMENT_PREPARATION = "ASSIGNMENT_PREPARATION"
    EXAM_PREPARATION = "EXAM_PREPARATION"
    RECOMMENDATION = "RECOMMENDATION"


class RoadmapItemOrigin(str, Enum):
    """DETERMINISTIC items are pure functions of the student's own Task/
    Course data (see app/services/roadmap_scheduling.py) -- never an LLM
    call. AI_GENERATED items are the LLM's prioritization/workload
    recommendations (app/services/roadmap_generation.py's Generate step),
    always structurally ground-truth-filtered against real task/course ids
    before being persisted. This field is the "distinguishable from
    official/structured facts" requirement made queryable, not just a
    display label."""

    DETERMINISTIC = "DETERMINISTIC"
    AI_GENERATED = "AI_GENERATED"


class SemesterRoadmap(Base):
    """One roadmap per semester (enforced by the unique constraint on
    semester_id) -- regenerating replaces it in place rather than creating
    a new row, with `version` incrementing each successful pass."""

    __tablename__ = "semester_roadmaps"

    id: Mapped[int] = mapped_column(primary_key=True)

    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    status: Mapped[RoadmapGenerationStatus] = mapped_column(
        SQLEnum(RoadmapGenerationStatus, name="roadmapgenerationstatus"),
        nullable=False,
        default=RoadmapGenerationStatus.NOT_REQUESTED,
        server_default=RoadmapGenerationStatus.NOT_REQUESTED.value,
    )

    # Starts at 0 ("never successfully generated"); mark_completed
    # increments it every successful pass, so the first real generation
    # becomes version 1 -- matching the "roadmap v1 -> edit -> regenerate
    # -> v2" framing in PHASE_09_SEMESTER_ROADMAP.md, not an off-by-one.
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    generation_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    # Populated when the deterministic pass succeeds (status still
    # COMPLETED) but the LLM recommendation pass didn't run or failed --
    # e.g. no LLM_PROVIDER configured. Distinct from generation_error,
    # which means the whole roadmap failed. See roadmap_generation.py.
    recommendations_unavailable_reason: Mapped[str | None] = mapped_column(
        Text,
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

    semester: Mapped["Semester"] = relationship()

    weeks: Mapped[list["RoadmapWeek"]] = relationship(
        back_populates="roadmap",
        order_by="RoadmapWeek.week_number",
    )


class RoadmapWeek(Base):
    __tablename__ = "roadmap_weeks"

    __table_args__ = (
        UniqueConstraint("roadmap_id", "week_number", name="uq_roadmap_week_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    roadmap_id: Mapped[int] = mapped_column(
        ForeignKey("semester_roadmaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    week_number: Mapped[int] = mapped_column(Integer, nullable=False)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)

    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    roadmap: Mapped["SemesterRoadmap"] = relationship(back_populates="weeks")

    items: Mapped[list["RoadmapItem"]] = relationship(
        back_populates="week",
        order_by="RoadmapItem.id",
    )


class RoadmapItem(Base):
    """`roadmap_id` is denormalized from week->roadmap (a light version of
    the same query-convenience tradeoff Phase 07 documented for
    DocumentChunk) so listing/ownership queries don't need an extra join.
    `is_user_edited` is the load-bearing field for this phase's edit-
    preservation acceptance criterion -- see
    app/services/roadmap_generation.py's regeneration logic and
    app/services/roadmap_item_update.py, the only writer of this field
    from a live request."""

    __tablename__ = "roadmap_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    week_id: Mapped[int] = mapped_column(
        ForeignKey("roadmap_weeks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    roadmap_id: Mapped[int] = mapped_column(
        ForeignKey("semester_roadmaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_type: Mapped[RoadmapItemType] = mapped_column(
        SQLEnum(RoadmapItemType, name="roadmapitemtype"),
        nullable=False,
    )

    origin: Mapped[RoadmapItemOrigin] = mapped_column(
        SQLEnum(RoadmapItemOrigin, name="roadmapitemorigin"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )

    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)

    is_user_edited: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
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

    week: Mapped["RoadmapWeek"] = relationship(back_populates="items")

    task: Mapped["Task | None"] = relationship()

    course: Mapped["Course | None"] = relationship()
