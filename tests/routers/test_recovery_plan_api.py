from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.main import app
from app.models.task import TaskPriority
from app.routers.recovery_plan import get_recovery_plan_service
from app.schemas.recovery_plan import RecoveryPlanResponse
from app.services.recovery_plan_generation import RecoveryPlanService


def make_plan(**overrides):
    defaults = dict(
        generated_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        items=[
            dict(
                task_id=1, title="Overdue essay", course_id=9,
                due_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
                is_overdue=True, urgency_label="overdue", cluster_size=0,
                estimated_effort_minutes=120, priority=TaskPriority.URGENT,
                score=100.0, explanation="Do this first.",
            )
        ],
        recommendations_unavailable_reason=None,
    )
    defaults.update(overrides)
    return RecoveryPlanResponse(**defaults)


@pytest.fixture
def service() -> MagicMock:
    return MagicMock(spec=RecoveryPlanService)


@pytest.fixture
def client(service):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=42)
    app.dependency_overrides[get_recovery_plan_service] = lambda: service
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def test_get_recovery_plan_requires_authentication(service):
    app.dependency_overrides[get_recovery_plan_service] = lambda: service
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.get("/api/v1/recovery-plan")

    test_client.close()
    app.dependency_overrides.clear()
    assert response.status_code == 401
    service.build_plan.assert_not_called()


def test_get_recovery_plan_returns_the_prioritized_plan(client, service):
    service.build_plan.return_value = make_plan()

    response = client.get("/api/v1/recovery-plan")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["priority"] == "urgent"
    assert body["items"][0]["explanation"] == "Do this first."
    service.build_plan.assert_called_once_with(user_id=42)


def test_get_recovery_plan_surfaces_the_unavailable_reason(client, service):
    service.build_plan.return_value = make_plan(recommendations_unavailable_reason="no provider")

    response = client.get("/api/v1/recovery-plan")

    assert response.status_code == 200
    assert response.json()["recommendations_unavailable_reason"] == "no provider"


def test_get_recovery_plan_returns_an_empty_list_for_no_tasks(client, service):
    service.build_plan.return_value = make_plan(items=[])

    response = client.get("/api/v1/recovery-plan")

    assert response.status_code == 200
    assert response.json()["items"] == []
