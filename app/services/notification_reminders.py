"""Cross-user deadline-reminder detection and sending — see
PHASE_13_NOTIFICATIONS.md.

Unlike every other service in this codebase, this one deliberately is
NOT scoped to a single user_id -- it's the body of a periodic system job
(app/worker/tasks/notifications.py) that needs to look across every
student's tasks at once. `NotificationService`'s own preference/dedup
checks still apply per (user, event), so this never sends anything a
single-user code path wouldn't also have respected.

WEEKLY_PLAN and RECOVERY_PLAN reminder types are defined (see
app/models/notification.py) but not sent by this service -- deliberately
out of scope this phase, see PHASE_13_NOTIFICATIONS.md's Remaining
Limitations for why.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.course import Course
from app.models.notification import NotificationType
from app.models.semester import Semester
from app.models.task import Task, TaskStatus, TaskType
from app.models.user import User
from app.services.notification_service import NotificationService
from app.services.notifications.exceptions import (
    NotificationNotConfiguredError,
    NotificationProviderError,
    NotificationTransientError,
)

logger = logging.getLogger(__name__)

DUE_SOON_WINDOW = timedelta(hours=24)
_EXAM_LIKE_TYPES = {TaskType.EXAM, TaskType.QUIZ}


def _due_soon_tasks_with_owner(db: Session, *, now: datetime) -> list[tuple[Task, User]]:
    return (
        db.query(Task, User)
        .join(Course, Task.course_id == Course.id)
        .join(Semester, Course.semester_id == Semester.id)
        .join(User, Semester.user_id == User.id)
        .filter(
            Task.is_deleted.is_(False),
            Course.is_deleted.is_(False),
            Semester.is_deleted.is_(False),
            Task.status.in_((TaskStatus.TODO, TaskStatus.IN_PROGRESS)),
            Task.due_at.is_not(None),
            Task.due_at >= now,
            Task.due_at <= now + DUE_SOON_WINDOW,
        )
        .all()
    )


def _overdue_tasks_with_owner(db: Session, *, now: datetime) -> list[tuple[Task, User]]:
    return (
        db.query(Task, User)
        .join(Course, Task.course_id == Course.id)
        .join(Semester, Course.semester_id == Semester.id)
        .join(User, Semester.user_id == User.id)
        .filter(
            Task.is_deleted.is_(False),
            Course.is_deleted.is_(False),
            Semester.is_deleted.is_(False),
            Task.status.in_((TaskStatus.TODO, TaskStatus.IN_PROGRESS)),
            Task.due_at.is_not(None),
            Task.due_at < now,
        )
        .all()
    )


class NotificationReminderService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.notification_service = notification_service or NotificationService(db, settings)

    def send_task_reminders(self, *, current_time: datetime | None = None) -> dict:
        now = current_time or datetime.now(timezone.utc)
        sent = 0
        skipped = 0
        failed = 0

        due_soon = [
            (task, user, self._due_soon_type(task))
            for task, user in _due_soon_tasks_with_owner(self.db, now=now)
        ]
        overdue = [
            (task, user, NotificationType.OVERDUE_TASK)
            for task, user in _overdue_tasks_with_owner(self.db, now=now)
        ]

        for task, user, notification_type in due_soon + overdue:
            try:
                log = self.notification_service.send_reminder(
                    user_id=user.id,
                    to_email=user.email,
                    notification_type=notification_type,
                    reference_id=str(task.id),
                    subject=self._subject_for(notification_type, task),
                    body=self._body_for(notification_type, task),
                )
            except (
                NotificationNotConfiguredError,
                NotificationTransientError,
                NotificationProviderError,
            ) as exc:
                # One student's/task's failure must never block the rest
                # of the run -- log and keep going, same "isolate the
                # blast radius" reasoning as Phase 03's non-fatal cleanup
                # hooks, applied to a batch job instead of a single call.
                logger.warning(
                    "Failed to send task reminder",
                    extra={"task_id": task.id, "user_id": user.id, "error": str(exc)},
                )
                failed += 1
                continue

            if log is None:
                skipped += 1
            else:
                sent += 1

        return {"sent": sent, "skipped": skipped, "failed": failed}

    @staticmethod
    def _due_soon_type(task: Task) -> NotificationType:
        return (
            NotificationType.EXAM_COUNTDOWN
            if task.task_type in _EXAM_LIKE_TYPES
            else NotificationType.ASSIGNMENT_DUE
        )

    @staticmethod
    def _subject_for(notification_type: NotificationType, task: Task) -> str:
        if notification_type == NotificationType.OVERDUE_TASK:
            return f"Overdue: {task.title}"
        if notification_type == NotificationType.EXAM_COUNTDOWN:
            return f"Upcoming exam: {task.title}"
        return f"Reminder: {task.title} is due soon"

    @staticmethod
    def _body_for(notification_type: NotificationType, task: Task) -> str:
        due = task.due_at.isoformat() if task.due_at else "an unknown time"
        if notification_type == NotificationType.OVERDUE_TASK:
            return f"Your task '{task.title}' was due at {due} and is still not complete."
        return f"Your task '{task.title}' is due at {due}."
