"""CalendarSyncService tests -- see PHASE_12_CALENDAR.md.

The mandated acceptance-criteria test is
test_sync_task_twice_updates_instead_of_creating_a_second_event below:
running sync twice must never create a duplicate event. Its counterpart,
test_unsync_task_removes_the_synced_event, is the other explicit
acceptance criterion (removing a task removes its synced event).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.exceptions.calendar import CalendarNotConnectedError
from app.models.calendar import CalendarConnection, CalendarSync, CalendarSyncStatus
from app.models.task import Task, TaskStatus, TaskType
from app.services.calendar.exceptions import CalendarProviderError
from app.services.calendar_oauth import TokenSet
from app.services.calendar_sync import CalendarSyncService
from tests.factories import create_user_with_semester_and_course


class FakeCalendarProvider:
    def __init__(self, *, create_error=None):
        self.created: list[tuple] = []
        self.updated: list[tuple] = []
        self.deleted: list[tuple] = []
        self._next_id = 1
        self._create_error = create_error

    def create_event(self, *, access_token, event):
        if self._create_error is not None:
            raise self._create_error
        event_id = f"evt-{self._next_id}"
        self._next_id += 1
        self.created.append((access_token, event))
        return event_id

    def update_event(self, *, access_token, provider_event_id, event):
        self.updated.append((access_token, provider_event_id, event))

    def delete_event(self, *, access_token, provider_event_id):
        self.deleted.append((access_token, provider_event_id))


class FakeOAuthService:
    def __init__(self):
        self.refresh_calls = 0

    def refresh_access_token(self, *, refresh_token):
        self.refresh_calls += 1
        return TokenSet(
            access_token="refreshed-access-token",
            refresh_token=refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )


def _add_task(db_session, *, course_id, title="Essay", due_at=None):
    task = Task(
        course_id=course_id, title=title, task_type=TaskType.ASSIGNMENT,
        status=TaskStatus.TODO, due_at=due_at, is_deleted=False,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _add_connection(db_session, user_id, *, expires_in=timedelta(hours=1)):
    connection = CalendarConnection(
        user_id=user_id,
        access_token="access-token",
        refresh_token="refresh-token",
        token_expires_at=datetime.now(timezone.utc) + expires_in,
    )
    db_session.add(connection)
    db_session.commit()
    return connection


def _build_service(db_session, *, provider=None, oauth_service=None):
    return CalendarSyncService(
        db=db_session,
        settings=SimpleNamespace(
            google_calendar_client_id="id", google_calendar_client_secret="secret",
            google_calendar_redirect_uri="https://example.com/callback",
        ),
        calendar_provider=provider or FakeCalendarProvider(),
        oauth_service=oauth_service or FakeOAuthService(),
    )


def test_sync_task_raises_when_not_connected(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="cal-noconn")
    task = _add_task(db_session, course_id=course.id, due_at=datetime.now(timezone.utc))
    service = _build_service(db_session)

    with pytest.raises(CalendarNotConnectedError):
        service.sync_task(task=task, user_id=user.id)


def test_sync_task_creates_an_event_when_none_exists(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="cal-create")
    _add_connection(db_session, user.id)
    task = _add_task(db_session, course_id=course.id, due_at=datetime.now(timezone.utc))
    provider = FakeCalendarProvider()
    service = _build_service(db_session, provider=provider)

    sync = service.sync_task(task=task, user_id=user.id)

    assert len(provider.created) == 1
    assert provider.updated == []
    assert sync.provider_event_id == "evt-1"
    assert sync.sync_status == CalendarSyncStatus.SYNCED


def test_sync_task_twice_updates_instead_of_creating_a_second_event(db_session):
    """The mandated acceptance-criteria test: re-running sync must never
    create a duplicate event."""
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="cal-idempotent")
    _add_connection(db_session, user.id)
    task = _add_task(db_session, course_id=course.id, due_at=datetime.now(timezone.utc))
    provider = FakeCalendarProvider()
    service = _build_service(db_session, provider=provider)

    first = service.sync_task(task=task, user_id=user.id)
    second = service.sync_task(task=task, user_id=user.id)

    assert len(provider.created) == 1  # only ever created once
    assert len(provider.updated) == 1  # the second call updated instead
    assert first.provider_event_id == second.provider_event_id
    assert provider.updated[0][1] == first.provider_event_id


def test_sync_task_marks_failed_on_provider_error(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="cal-provider-error")
    _add_connection(db_session, user.id)
    task = _add_task(db_session, course_id=course.id, due_at=datetime.now(timezone.utc))
    provider = FakeCalendarProvider(create_error=CalendarProviderError("rejected"))
    service = _build_service(db_session, provider=provider)

    with pytest.raises(CalendarProviderError):
        service.sync_task(task=task, user_id=user.id)

    sync = db_session.query(CalendarSync).filter(CalendarSync.task_id == task.id).first()
    assert sync.sync_status == CalendarSyncStatus.FAILED
    assert sync.sync_error is not None


def test_unsync_task_removes_the_synced_event(db_session):
    """The other mandated acceptance-criteria test: removing a task
    removes its synced event."""
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="cal-unsync")
    _add_connection(db_session, user.id)
    task = _add_task(db_session, course_id=course.id, due_at=datetime.now(timezone.utc))
    provider = FakeCalendarProvider()
    service = _build_service(db_session, provider=provider)
    sync = service.sync_task(task=task, user_id=user.id)

    service.unsync_task(task=task, user_id=user.id)

    assert provider.deleted == [("access-token", sync.provider_event_id)]
    remaining = db_session.query(CalendarSync).filter(CalendarSync.task_id == task.id).first()
    assert remaining is None


def test_unsync_task_never_synced_is_a_noop(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="cal-unsync-noop")
    _add_connection(db_session, user.id)
    task = _add_task(db_session, course_id=course.id, due_at=datetime.now(timezone.utc))
    provider = FakeCalendarProvider()
    service = _build_service(db_session, provider=provider)

    service.unsync_task(task=task, user_id=user.id)  # never synced -- must not raise

    assert provider.deleted == []


def test_sync_task_refreshes_an_expired_access_token_before_use(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="cal-refresh")
    _add_connection(db_session, user.id, expires_in=timedelta(minutes=1))  # inside the refresh margin
    task = _add_task(db_session, course_id=course.id, due_at=datetime.now(timezone.utc))
    provider = FakeCalendarProvider()
    oauth = FakeOAuthService()
    service = _build_service(db_session, provider=provider, oauth_service=oauth)

    service.sync_task(task=task, user_id=user.id)

    assert oauth.refresh_calls == 1
    assert provider.created[0][0] == "refreshed-access-token"
