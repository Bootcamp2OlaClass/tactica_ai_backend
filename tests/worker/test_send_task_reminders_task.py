"""Unit test for the send_task_reminders periodic task, run in Celery's
eager mode -- see PHASE_13_NOTIFICATIONS.md. No email provider is
configured in this test environment, which is fine here: the task's own
plumbing (does it run, does it return the expected shape) is what's
under test, not send quality -- already covered thoroughly against a
fake provider in tests/services/test_notification_reminders.py.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.task import Task, TaskStatus, TaskType
from app.worker.celery_app import celery_app
from app.worker.tasks import notifications as notifications_task_module
from app.worker.tasks.notifications import send_task_reminders
from tests.conftest import TEST_DATABASE_URL
from tests.factories import create_user_with_course


@pytest.fixture
def eager_mode():
    original_eager = celery_app.conf.task_always_eager
    original_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager = original_eager
    celery_app.conf.task_eager_propagates = original_propagates


@pytest.fixture(autouse=True)
def task_session_local(monkeypatch):
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    test_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    monkeypatch.setattr(notifications_task_module, "SessionLocal", test_session_local)
    yield
    engine.dispose()


def test_task_runs_and_reports_a_skipped_reminder_without_a_configured_provider(
    db_session, eager_mode
):
    # No RESEND_API_KEY in this test environment -- the deterministic
    # detection still finds the task, but the send attempt fails to
    # configure a provider, which the reminder service treats as a
    # per-item failure (logged, counted, never raised) rather than
    # crashing the whole periodic run.
    user, course = create_user_with_course(db_session, email_prefix="task-remind")
    task = Task(
        course_id=course.id, title="Essay", task_type=TaskType.ASSIGNMENT,
        status=TaskStatus.TODO, due_at=datetime.now(timezone.utc) + timedelta(hours=1),
        is_deleted=False,
    )
    db_session.add(task)
    db_session.commit()

    result = send_task_reminders.apply()

    assert result.successful()
    assert result.result["failed"] == 1
    assert result.result["sent"] == 0
