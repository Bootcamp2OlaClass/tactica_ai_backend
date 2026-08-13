"""NotificationReminderService tests -- see PHASE_13_NOTIFICATIONS.md.

This service is deliberately cross-user (a periodic system job, not a
single request), so these tests build multiple students' data in the
same test to prove reminders reach the right owner and respect each
one's own preferences independently.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.notification import NotificationType
from app.models.task import Task, TaskStatus, TaskType
from app.services.notification_reminders import NotificationReminderService
from app.services.notification_service import NotificationService
from tests.factories import create_user_with_course

NOW = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)


class FakeNotificationProvider:
    def __init__(self):
        self.sent: list[tuple] = []

    def send_email(self, *, to, subject, body):
        self.sent.append((to, subject, body))
        return f"msg-{len(self.sent)}"


def _add_task(db_session, *, course_id, title="Task", due_at, task_type=TaskType.ASSIGNMENT):
    task = Task(
        course_id=course_id, title=title, task_type=task_type,
        status=TaskStatus.TODO, due_at=due_at, is_deleted=False,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _build_service(db_session, *, provider=None):
    notification_service = NotificationService(
        db=db_session, settings=SimpleNamespace(), provider=provider or FakeNotificationProvider()
    )
    return NotificationReminderService(
        db=db_session, settings=SimpleNamespace(), notification_service=notification_service
    ), notification_service


def test_sends_assignment_due_reminder_for_a_task_due_within_24_hours(db_session):
    user, course = create_user_with_course(db_session, email_prefix="remind-due-soon")
    _add_task(db_session, course_id=course.id, due_at=NOW + timedelta(hours=5))
    provider = FakeNotificationProvider()
    service, _ = _build_service(db_session, provider=provider)

    result = service.send_task_reminders(current_time=NOW)

    assert result["sent"] == 1
    assert provider.sent[0][0] == user.email


def test_sends_exam_countdown_instead_of_assignment_due_for_exam_type_tasks(db_session):
    user, course = create_user_with_course(db_session, email_prefix="remind-exam")
    _add_task(db_session, course_id=course.id, due_at=NOW + timedelta(hours=5), task_type=TaskType.EXAM)
    provider = FakeNotificationProvider()
    service, _ = _build_service(db_session, provider=provider)

    service.send_task_reminders(current_time=NOW)

    assert "Upcoming exam" in provider.sent[0][1]


def test_does_not_send_for_tasks_outside_the_due_soon_window(db_session):
    user, course = create_user_with_course(db_session, email_prefix="remind-too-far")
    _add_task(db_session, course_id=course.id, due_at=NOW + timedelta(days=5))
    provider = FakeNotificationProvider()
    service, _ = _build_service(db_session, provider=provider)

    result = service.send_task_reminders(current_time=NOW)

    assert result["sent"] == 0
    assert provider.sent == []


def test_sends_overdue_reminder_for_a_task_past_its_due_date(db_session):
    user, course = create_user_with_course(db_session, email_prefix="remind-overdue")
    _add_task(db_session, course_id=course.id, due_at=NOW - timedelta(hours=2))
    provider = FakeNotificationProvider()
    service, _ = _build_service(db_session, provider=provider)

    result = service.send_task_reminders(current_time=NOW)

    assert result["sent"] == 1
    assert "Overdue" in provider.sent[0][1]


def test_reaches_each_users_own_tasks_only(db_session):
    user_a, course_a = create_user_with_course(db_session, email_prefix="remind-multi-a")
    user_b, course_b = create_user_with_course(db_session, email_prefix="remind-multi-b")
    _add_task(db_session, course_id=course_a.id, title="A's task", due_at=NOW + timedelta(hours=1))
    _add_task(db_session, course_id=course_b.id, title="B's task", due_at=NOW + timedelta(hours=1))
    provider = FakeNotificationProvider()
    service, _ = _build_service(db_session, provider=provider)

    result = service.send_task_reminders(current_time=NOW)

    assert result["sent"] == 2
    recipients = {sent[0] for sent in provider.sent}
    assert recipients == {user_a.email, user_b.email}


def test_respects_a_users_own_opted_out_preference(db_session):
    user, course = create_user_with_course(db_session, email_prefix="remind-opted-out")
    _add_task(db_session, course_id=course.id, due_at=NOW + timedelta(hours=1))
    provider = FakeNotificationProvider()
    service, notification_service = _build_service(db_session, provider=provider)
    notification_service.set_preference(
        user_id=user.id, notification_type=NotificationType.ASSIGNMENT_DUE, enabled=False
    )

    result = service.send_task_reminders(current_time=NOW)

    assert result["sent"] == 0
    assert result["skipped"] == 1
    assert provider.sent == []


def test_running_twice_never_sends_duplicate_reminders(db_session):
    """The same underlying acceptance criterion (dedup), now proven at
    the level of the actual scheduled job -- two separate runs of the
    periodic task must not double-send."""
    user, course = create_user_with_course(db_session, email_prefix="remind-run-twice")
    _add_task(db_session, course_id=course.id, due_at=NOW + timedelta(hours=1))
    provider = FakeNotificationProvider()
    service, _ = _build_service(db_session, provider=provider)

    service.send_task_reminders(current_time=NOW)
    service.send_task_reminders(current_time=NOW + timedelta(minutes=15))  # next scheduled tick

    assert len(provider.sent) == 1
