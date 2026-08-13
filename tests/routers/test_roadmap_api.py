from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.exceptions.roadmap import (
    RoadmapGenerationAlreadyInProgressError,
    RoadmapItemNotFoundError,
    RoadmapNotFoundError,
    RoadmapQueueUnavailableError,
)
from app.exceptions.semester import SemesterNotFoundError
from app.main import app
from app.models.roadmap import RoadmapGenerationStatus, RoadmapItemOrigin, RoadmapItemType
from app.routers.roadmap import (
    get_roadmap_generation_trigger_service,
    get_roadmap_item_update_service,
    get_roadmap_query_service,
)
from app.services.roadmap_generation_trigger import RoadmapGenerationTriggerService
from app.services.roadmap_item_update import RoadmapItemUpdateService
from app.services.roadmap_query import RoadmapQueryService


def make_item(**overrides):
    defaults = dict(
        id=1, week_id=1, item_type=RoadmapItemType.ASSIGNMENT_PREPARATION,
        origin=RoadmapItemOrigin.DETERMINISTIC, title="Work on Essay 1", description=None,
        task_id=5, course_id=9, due_date=date(2026, 8, 26), is_user_edited=False,
        created_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_week(**overrides):
    defaults = dict(
        id=1, week_number=1, start_date=date(2026, 8, 24), end_date=date(2026, 8, 30),
        items=[make_item()],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_roadmap(**overrides):
    defaults = dict(
        id=1, semester_id=10, status=RoadmapGenerationStatus.COMPLETED, version=1,
        generated_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        generation_error=None, recommendations_unavailable_reason=None,
        weeks=[make_week()],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def trigger_service() -> MagicMock:
    return MagicMock(spec=RoadmapGenerationTriggerService)


@pytest.fixture
def query_service() -> MagicMock:
    return MagicMock(spec=RoadmapQueryService)


@pytest.fixture
def update_service() -> MagicMock:
    return MagicMock(spec=RoadmapItemUpdateService)


@pytest.fixture
def client(trigger_service, query_service, update_service):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=42)
    app.dependency_overrides[get_roadmap_generation_trigger_service] = lambda: trigger_service
    app.dependency_overrides[get_roadmap_query_service] = lambda: query_service
    app.dependency_overrides[get_roadmap_item_update_service] = lambda: update_service
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def test_trigger_generation_requires_authentication(trigger_service):
    app.dependency_overrides[get_roadmap_generation_trigger_service] = lambda: trigger_service
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.post("/api/v1/semesters/10/roadmap/generate")

    test_client.close()
    app.dependency_overrides.clear()
    assert response.status_code == 401
    trigger_service.trigger_generation.assert_not_called()


def test_trigger_generation_success_returns_202(client, trigger_service):
    trigger_service.trigger_generation.return_value = make_roadmap(status=RoadmapGenerationStatus.QUEUED)

    response = client.post("/api/v1/semesters/10/roadmap/generate")

    assert response.status_code == 202
    trigger_service.trigger_generation.assert_called_once_with(semester_id=10, user_id=42)
    assert response.json()["status"] == "QUEUED"


def test_trigger_generation_semester_not_found_returns_404(client, trigger_service):
    trigger_service.trigger_generation.side_effect = SemesterNotFoundError("nope")

    response = client.post("/api/v1/semesters/10/roadmap/generate")

    assert response.status_code == 404


def test_trigger_generation_already_in_progress_returns_409(client, trigger_service):
    trigger_service.trigger_generation.side_effect = RoadmapGenerationAlreadyInProgressError("running")

    response = client.post("/api/v1/semesters/10/roadmap/generate")

    assert response.status_code == 409


def test_trigger_generation_queue_unavailable_returns_503(client, trigger_service):
    trigger_service.trigger_generation.side_effect = RoadmapQueueUnavailableError("no broker")

    response = client.post("/api/v1/semesters/10/roadmap/generate")

    assert response.status_code == 503


def test_get_roadmap_success_returns_full_structure(client, query_service):
    query_service.get_roadmap.return_value = make_roadmap()

    response = client.get("/api/v1/semesters/10/roadmap")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert len(body["weeks"]) == 1
    assert len(body["weeks"][0]["items"]) == 1
    assert body["weeks"][0]["items"][0]["origin"] == "DETERMINISTIC"
    query_service.get_roadmap.assert_called_once_with(semester_id=10, user_id=42)


def test_get_roadmap_not_generated_yet_returns_404(client, query_service):
    query_service.get_roadmap.side_effect = RoadmapNotFoundError("none yet")

    response = client.get("/api/v1/semesters/10/roadmap")

    assert response.status_code == 404


def test_get_roadmap_semester_not_found_returns_404(client, query_service):
    query_service.get_roadmap.side_effect = SemesterNotFoundError("nope")

    response = client.get("/api/v1/semesters/10/roadmap")

    assert response.status_code == 404


def test_update_roadmap_item_success(client, update_service):
    update_service.update_item.return_value = make_item(title="Edited", is_user_edited=True)

    response = client.patch("/api/v1/roadmap-items/1", json={"title": "Edited"})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Edited"
    assert body["is_user_edited"] is True
    update_service.update_item.assert_called_once_with(
        item_id=1, user_id=42, title="Edited", description=None
    )


def test_update_roadmap_item_not_found_returns_404(client, update_service):
    update_service.update_item.side_effect = RoadmapItemNotFoundError("nope")

    response = client.patch("/api/v1/roadmap-items/1", json={"title": "Edited"})

    assert response.status_code == 404
