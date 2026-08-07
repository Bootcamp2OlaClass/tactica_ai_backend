from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.repositories.dashboard import DashboardRepository
from app.services.semester import SemesterService


class DashboardService:
    """Compose the authenticated user's dashboard summary."""

    def __init__(
        self,
        db: Session,
        repository: DashboardRepository | None = None,
        semester_service: SemesterService | None = None,
    ) -> None:
        self.repository = repository or DashboardRepository(db)
        self.semester_service = semester_service or SemesterService(db)

    def get_summary(
        self,
        user_id: int,
        current_time: datetime | None = None,
        upcoming_limit: int = 5,
        recent_documents_limit: int = 5,
    ) -> dict[str, object]:
        """Return dashboard counts and bounded recent/upcoming records."""

        now = current_time or datetime.now(timezone.utc)
        due_soon_until = now + timedelta(days=7)

        current_semester = self.semester_service.get_current_semester(
            user_id=user_id,
            current_date=now.date(),
        )
        active_course_count = self.repository.count_active_courses(
            user_id=user_id,
        )
        task_counts = self.repository.get_task_counts(
            user_id=user_id,
            current_time=now,
            due_soon_until=due_soon_until,
        )
        upcoming_deadlines = self.repository.list_upcoming_deadlines(
            user_id=user_id,
            current_time=now,
            limit=upcoming_limit,
        )
        recent_documents = self.repository.list_recent_documents(
            user_id=user_id,
            limit=recent_documents_limit,
        )

        return {
            "current_semester": current_semester,
            "active_course_count": active_course_count,
            "incomplete_task_count": task_counts["incomplete"],
            "overdue_task_count": task_counts["overdue"],
            "tasks_due_within_seven_days_count": task_counts[
                "due_within_seven_days"
            ],
            "upcoming_deadlines": upcoming_deadlines,
            "recent_documents": recent_documents,
        }
