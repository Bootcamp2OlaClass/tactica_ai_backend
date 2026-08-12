from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.semester import Semester, SemesterStatus
from app.services.dashboard import DashboardService


@pytest.fixture
def repository() -> MagicMock:
    return MagicMock()


@pytest.fixture
def semester_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(
    repository: MagicMock,
    semester_service: MagicMock,
) -> DashboardService:
    return DashboardService(
        db=MagicMock(),
        repository=repository,
        semester_service=semester_service,
    )


def test_get_summary_composes_user_dashboard(
    service: DashboardService,
    repository: MagicMock,
    semester_service: MagicMock,
) -> None:
    now = datetime(2026, 8, 8, 9, 30, tzinfo=timezone.utc)
    semester = Semester(
        id=1,
        user_id=42,
        name="Fall",
        academic_year=2026,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 12, 20),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )
    deadlines = [MagicMock(id=1), MagicMock(id=2)]
    documents = [MagicMock(id=3), MagicMock(id=4)]
    semester_service.get_current_semester.return_value = semester
    repository.count_active_courses.return_value = 3
    repository.get_task_counts.return_value = {
        "incomplete": 8,
        "overdue": 2,
        "due_within_seven_days": 4,
    }
    repository.list_upcoming_deadlines.return_value = deadlines
    repository.list_recent_documents.return_value = documents

    result = service.get_summary(
        user_id=42,
        current_time=now,
        upcoming_limit=6,
        recent_documents_limit=4,
    )

    assert result == {
        "current_semester": semester,
        "active_course_count": 3,
        "incomplete_task_count": 8,
        "overdue_task_count": 2,
        "tasks_due_within_seven_days_count": 4,
        "upcoming_deadlines": deadlines,
        "recent_documents": documents,
    }
    semester_service.get_current_semester.assert_called_once_with(
        user_id=42,
        current_date=now.date(),
    )
    repository.count_active_courses.assert_called_once_with(user_id=42)
    repository.get_task_counts.assert_called_once_with(
        user_id=42,
        current_time=now,
        due_soon_until=now + timedelta(days=7),
    )
    repository.list_upcoming_deadlines.assert_called_once_with(
        user_id=42,
        current_time=now,
        limit=6,
    )
    repository.list_recent_documents.assert_called_once_with(
        user_id=42,
        limit=4,
    )


def test_empty_account_returns_valid_empty_summary(
    service: DashboardService,
    repository: MagicMock,
    semester_service: MagicMock,
) -> None:
    semester_service.get_current_semester.return_value = None
    repository.count_active_courses.return_value = 0
    repository.get_task_counts.return_value = {
        "incomplete": 0,
        "overdue": 0,
        "due_within_seven_days": 0,
    }
    repository.list_upcoming_deadlines.return_value = []
    repository.list_recent_documents.return_value = []

    result = service.get_summary(
        user_id=99,
        current_time=datetime(2026, 8, 8, tzinfo=timezone.utc),
    )

    assert result == {
        "current_semester": None,
        "active_course_count": 0,
        "incomplete_task_count": 0,
        "overdue_task_count": 0,
        "tasks_due_within_seven_days_count": 0,
        "upcoming_deadlines": [],
        "recent_documents": [],
    }


def test_default_clock_is_timezone_aware(
    service: DashboardService,
    repository: MagicMock,
    semester_service: MagicMock,
) -> None:
    semester_service.get_current_semester.return_value = None
    repository.count_active_courses.return_value = 0
    repository.get_task_counts.return_value = {
        "incomplete": 0,
        "overdue": 0,
        "due_within_seven_days": 0,
    }
    repository.list_upcoming_deadlines.return_value = []
    repository.list_recent_documents.return_value = []

    service.get_summary(user_id=1)

    now = repository.get_task_counts.call_args.kwargs["current_time"]
    due_until = repository.get_task_counts.call_args.kwargs[
        "due_soon_until"
    ]
    assert now.tzinfo is not None
    assert due_until - now == timedelta(days=7)
