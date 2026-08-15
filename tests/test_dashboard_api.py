from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.exceptions.semester import SemesterConflictError
from app.main import app
from app.models.document import ProcessingStatus
from app.models.semester import SemesterStatus
from app.models.task import TaskPriority, TaskStatus, TaskType
from app.routers.dashboard import get_dashboard_service
from app.services.dashboard import DashboardService


def make_summary() -> dict[str, object]:
    return {
        "current_semester": SimpleNamespace(
            id=7,
            user_id=42,
            name="Fall 2026",
            academic_year=2026,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 12, 20),
            status=SemesterStatus.ACTIVE,
            description="Current semester",
            created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        ),
        "active_course_count": 3,
        "incomplete_task_count": 8,
        "overdue_task_count": 2,
        "tasks_due_within_seven_days_count": 4,
        "upcoming_deadlines": [
            SimpleNamespace(
                id=11,
                course_id=5,
                title="Submit project",
                task_type=TaskType.PROJECT,
                status=TaskStatus.IN_PROGRESS,
                priority=TaskPriority.HIGH,
                due_at=datetime(
                    2026, 8, 10, 16, 0, tzinfo=timezone.utc
                ),
            )
        ],
        "recent_documents": [
            # Matches the real Document ORM model's attribute names
            # (app/models/document.py), not DashboardDocumentResponse's
            # shorter public field names -- the service returns actual
            # Document rows, and this fixture previously used the
            # response-schema names directly (file_name/status), which
            # made this test pass against a shape that could never occur
            # in production and hid a real 500 (DashboardDocumentResponse
            # field/attribute mismatch, fixed via validation_alias in
            # app/schemas/dashboard.py).
            SimpleNamespace(
                id=21,
                course_id=5,
                original_file_name="syllabus.pdf",
                processing_status=ProcessingStatus.COMPLETED,
                created_at=datetime(
                    2026, 8, 8, 8, 0, tzinfo=timezone.utc
                ),
            )
        ],
    }


@pytest.fixture
def service() -> MagicMock:
    return MagicMock(spec=DashboardService)


@pytest.fixture
def client(service: MagicMock):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=42
    )
    app.dependency_overrides[get_dashboard_service] = lambda: service
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def test_dashboard_requires_authentication(service: MagicMock) -> None:
    app.dependency_overrides[get_dashboard_service] = lambda: service
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.get("/api/v1/dashboard")

    test_client.close()
    app.dependency_overrides.clear()
    assert response.status_code == 401
    service.get_summary.assert_not_called()


def test_dashboard_returns_all_sections_for_authenticated_user(
    client: TestClient,
    service: MagicMock,
) -> None:
    service.get_summary.return_value = make_summary()

    response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    service.get_summary.assert_called_once_with(user_id=42)
    payload = response.json()
    assert payload["current_semester"]["id"] == 7
    assert payload["active_course_count"] == 3
    assert payload["incomplete_task_count"] == 8
    assert payload["overdue_task_count"] == 2
    assert payload["tasks_due_within_seven_days_count"] == 4
    assert payload["upcoming_deadlines"][0]["id"] == 11
    assert payload["recent_documents"][0]["id"] == 21
    assert payload["current_semester"]["start_date"] == "2026-08-01"
    assert payload["upcoming_deadlines"][0]["due_at"] == (
        "2026-08-10T16:00:00Z"
    )


def test_empty_dashboard_returns_200_with_arrays_and_numeric_counts(
    client: TestClient,
    service: MagicMock,
) -> None:
    service.get_summary.return_value = {
        "current_semester": None,
        "active_course_count": 0,
        "incomplete_task_count": 0,
        "overdue_task_count": 0,
        "tasks_due_within_seven_days_count": 0,
        "upcoming_deadlines": [],
        "recent_documents": [],
    }

    response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_semester"] is None
    assert payload["upcoming_deadlines"] == []
    assert payload["recent_documents"] == []
    for field in (
        "active_course_count",
        "incomplete_task_count",
        "overdue_task_count",
        "tasks_due_within_seven_days_count",
    ):
        assert isinstance(payload[field], int)
        assert payload[field] == 0


def test_dashboard_returns_409_for_multiple_active_semesters(
    client: TestClient,
    service: MagicMock,
) -> None:
    # A user with two ACTIVE semesters is a genuine data-conflict state, not
    # a server bug -- the dashboard must surface it as 409, never as an
    # unhandled 500 (root cause of the reported dashboard outage was
    # infra/DB-reachability, not this path, but this conflict path is the
    # one place the service is documented to intentionally raise).
    service.get_summary.side_effect = SemesterConflictError(
        "Multiple active semesters exist for this user."
    )

    response = client.get("/api/v1/dashboard")

    assert response.status_code == 409


def test_openapi_documents_complete_dashboard_response() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/v1/dashboard"]["get"]

    assert operation["security"] == [{"HTTPBearer": []}]
    response_schema = operation["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert response_schema["$ref"].endswith("/DashboardSummaryResponse")

    dashboard_schema = schema["components"]["schemas"][
        "DashboardSummaryResponse"
    ]
    assert set(dashboard_schema["required"]) == {
        "current_semester",
        "active_course_count",
        "incomplete_task_count",
        "overdue_task_count",
        "tasks_due_within_seven_days_count",
        "upcoming_deadlines",
        "recent_documents",
    }
