from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.course import Course, CourseStatus
from app.models.document import Document
from app.models.semester import Semester
from app.models.task import Task, TaskStatus


INCOMPLETE_TASK_STATUSES = (
    TaskStatus.TODO,
    TaskStatus.IN_PROGRESS,
)


class DashboardRepository:
    """Run bounded and aggregate queries used by the dashboard."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def count_active_courses(self, user_id: int) -> int:
        statement = (
            select(func.count(Course.id))
            .join(Semester, Course.semester_id == Semester.id)
            .where(
                Semester.user_id == user_id,
                Semester.is_deleted.is_(False),
                Course.is_deleted.is_(False),
                Course.status == CourseStatus.ACTIVE,
            )
        )

        return self.db.scalar(statement) or 0

    def get_task_counts(
        self,
        user_id: int,
        current_time: datetime,
        due_soon_until: datetime,
    ) -> dict[str, int]:
        """Return all dashboard task counts in one aggregate query."""

        incomplete = Task.status.in_(INCOMPLETE_TASK_STATUSES)
        statement = (
            select(
                func.sum(case((incomplete, 1), else_=0)),
                func.sum(
                    case(
                        (
                            incomplete
                            & Task.due_at.is_not(None)
                            & (Task.due_at < current_time),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            incomplete
                            & Task.due_at.is_not(None)
                            & (Task.due_at >= current_time)
                            & (Task.due_at <= due_soon_until),
                            1,
                        ),
                        else_=0,
                    )
                ),
            )
            .select_from(Task)
            .join(Course, Task.course_id == Course.id)
            .join(Semester, Course.semester_id == Semester.id)
            .where(
                Semester.user_id == user_id,
                Semester.is_deleted.is_(False),
                Course.is_deleted.is_(False),
                Task.is_deleted.is_(False),
            )
        )

        row = self.db.execute(statement).one()

        return {
            "incomplete": row[0] or 0,
            "overdue": row[1] or 0,
            "due_within_seven_days": row[2] or 0,
        }

    def list_upcoming_deadlines(
        self,
        user_id: int,
        current_time: datetime,
        limit: int,
    ) -> list[Task]:
        statement = (
            select(Task)
            .join(Course, Task.course_id == Course.id)
            .join(Semester, Course.semester_id == Semester.id)
            .where(
                Semester.user_id == user_id,
                Semester.is_deleted.is_(False),
                Course.is_deleted.is_(False),
                Task.is_deleted.is_(False),
                Task.status.in_(INCOMPLETE_TASK_STATUSES),
                Task.due_at.is_not(None),
                Task.due_at >= current_time,
            )
            .order_by(Task.due_at.asc(), Task.id.asc())
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())

    def list_recent_documents(
        self,
        user_id: int,
        limit: int,
    ) -> list[Document]:
        statement = (
            select(Document)
            .join(Course, Document.course_id == Course.id)
            .join(Semester, Course.semester_id == Semester.id)
            .where(
                Semester.user_id == user_id,
                Semester.is_deleted.is_(False),
                Course.is_deleted.is_(False),
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())
