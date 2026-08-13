"""Deterministic academic-context snapshot for the Coach's Retrieve step —
see PHASE_08_AI_STUDY_COACH.md. Reuses DashboardRepository/course_repository
rather than re-querying from scratch, since this is exactly the data the
dashboard already aggregates for the same user.

Deliberately not RAG: this is the student's own structured DB data
(courses, deadlines), not document text, so no embedding/retrieval is
needed or appropriate -- it's just a plain, cheap, deterministic query.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.course import CourseStatus
from app.repositories import course_repository
from app.repositories.dashboard import DashboardRepository


@dataclass(frozen=True)
class AcademicContext:
    course_names: list[str] = field(default_factory=list)
    upcoming_deadlines: list[str] = field(default_factory=list)
    overdue_count: int = 0

    def is_empty(self) -> bool:
        return not self.course_names and not self.upcoming_deadlines


class AcademicContextService:
    def __init__(
        self,
        db: Session,
        dashboard_repository: DashboardRepository | None = None,
    ) -> None:
        self.db = db
        self.dashboard_repository = dashboard_repository or DashboardRepository(db)

    def get_context(
        self, *, user_id: int, current_time: datetime | None = None
    ) -> AcademicContext:
        now = current_time or datetime.now(timezone.utc)

        courses = course_repository.list_courses_by_user(
            self.db, user_id=user_id, status=CourseStatus.ACTIVE, limit=50
        )
        deadlines = self.dashboard_repository.list_upcoming_deadlines(
            user_id=user_id, current_time=now, limit=10
        )
        task_counts = self.dashboard_repository.get_task_counts(
            user_id=user_id,
            current_time=now,
            due_soon_until=now + timedelta(days=7),
        )

        return AcademicContext(
            course_names=[
                f"{course.course_code} - {course.name}" for course in courses
            ],
            upcoming_deadlines=[
                f"{task.title} (due {task.due_at.date().isoformat()})"
                for task in deadlines
                if task.due_at is not None
            ],
            overdue_count=task_counts["overdue"],
        )
