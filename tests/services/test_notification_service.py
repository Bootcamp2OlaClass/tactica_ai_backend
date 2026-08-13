"""NotificationService tests -- see PHASE_13_NOTIFICATIONS.md.

The two phase-brief-mandated tests are
test_send_reminder_respects_an_opted_out_preference (an opted-out user
receives nothing) and test_send_reminder_never_sends_the_same_event_twice
(no duplicate sends for the same event) below.
"""

from types import SimpleNamespace

from app.models.notification import NotificationLog, NotificationType
from app.services.notification_service import NotificationService
from tests.factories import create_user_with_course


class FakeNotificationProvider:
    def __init__(self):
        self.sent: list[tuple] = []

    def send_email(self, *, to, subject, body):
        self.sent.append((to, subject, body))
        return f"msg-{len(self.sent)}"


def _build_service(db_session, *, provider=None):
    return NotificationService(
        db=db_session, settings=SimpleNamespace(), provider=provider or FakeNotificationProvider()
    )


def test_is_enabled_defaults_true_with_no_preference_row(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="notif-default")
    service = _build_service(db_session)

    assert service.is_enabled(user_id=user.id, notification_type=NotificationType.ASSIGNMENT_DUE) is True


def test_set_preference_persists_and_is_reflected(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="notif-set-pref")
    service = _build_service(db_session)

    service.set_preference(user_id=user.id, notification_type=NotificationType.OVERDUE_TASK, enabled=False)

    assert service.is_enabled(user_id=user.id, notification_type=NotificationType.OVERDUE_TASK) is False
    # Unrelated types are unaffected.
    assert service.is_enabled(user_id=user.id, notification_type=NotificationType.ASSIGNMENT_DUE) is True


def test_send_reminder_respects_an_opted_out_preference(db_session):
    """The mandated preference-respecting test: an opted-out user
    receives nothing."""
    user, _ = create_user_with_course(db_session, email_prefix="notif-opted-out")
    provider = FakeNotificationProvider()
    service = _build_service(db_session, provider=provider)
    service.set_preference(user_id=user.id, notification_type=NotificationType.ASSIGNMENT_DUE, enabled=False)

    result = service.send_reminder(
        user_id=user.id, to_email=user.email, notification_type=NotificationType.ASSIGNMENT_DUE,
        reference_id="task-1", subject="Reminder", body="Your task is due.",
    )

    assert result is None
    assert provider.sent == []


def test_send_reminder_sends_when_enabled(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="notif-enabled")
    provider = FakeNotificationProvider()
    service = _build_service(db_session, provider=provider)

    result = service.send_reminder(
        user_id=user.id, to_email=user.email, notification_type=NotificationType.ASSIGNMENT_DUE,
        reference_id="task-1", subject="Reminder", body="Your task is due.",
    )

    assert result is not None
    assert result.provider_message_id == "msg-1"
    assert len(provider.sent) == 1
    assert provider.sent[0][0] == user.email


def test_send_reminder_never_sends_the_same_event_twice(db_session):
    """The mandated dedup test: no duplicate sends for the same event,
    even across separate calls (e.g. two scheduled-job runs)."""
    user, _ = create_user_with_course(db_session, email_prefix="notif-dedup")
    provider = FakeNotificationProvider()
    service = _build_service(db_session, provider=provider)

    first = service.send_reminder(
        user_id=user.id, to_email=user.email, notification_type=NotificationType.ASSIGNMENT_DUE,
        reference_id="task-1", subject="Reminder", body="Your task is due.",
    )
    second = service.send_reminder(
        user_id=user.id, to_email=user.email, notification_type=NotificationType.ASSIGNMENT_DUE,
        reference_id="task-1", subject="Reminder", body="Your task is due.",
    )

    assert len(provider.sent) == 1  # only ever sent once
    assert first.id == second.id  # the second call returned the same log row


def test_send_reminder_dedup_is_scoped_per_notification_type(db_session):
    """The same reference_id under a different notification_type is a
    genuinely different event, not a duplicate -- e.g. an OVERDUE_TASK
    reminder for a task must still send even after an ASSIGNMENT_DUE
    reminder already went out for that same task."""
    user, _ = create_user_with_course(db_session, email_prefix="notif-dedup-scope")
    provider = FakeNotificationProvider()
    service = _build_service(db_session, provider=provider)

    service.send_reminder(
        user_id=user.id, to_email=user.email, notification_type=NotificationType.ASSIGNMENT_DUE,
        reference_id="task-1", subject="Due soon", body="...",
    )
    service.send_reminder(
        user_id=user.id, to_email=user.email, notification_type=NotificationType.OVERDUE_TASK,
        reference_id="task-1", subject="Overdue", body="...",
    )

    assert len(provider.sent) == 2


def test_list_preferences_returns_all_types_with_defaults(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="notif-list")
    service = _build_service(db_session)
    service.set_preference(user_id=user.id, notification_type=NotificationType.WEEKLY_PLAN, enabled=False)

    preferences = service.list_preferences(user_id=user.id)

    assert preferences[NotificationType.WEEKLY_PLAN] is False
    assert preferences[NotificationType.ASSIGNMENT_DUE] is True  # default, no row
    assert set(preferences.keys()) == set(NotificationType)
