from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.exceptions.calendar import CalendarNotConnectedError
from app.exceptions.task import TaskNotFoundError
from app.main import app
from app.models.calendar import CalendarSyncStatus
from app.routers.calendar import (
    get_calendar_connection_service,
    get_calendar_sync_service,
    get_task_service,
)
from app.services.calendar.exceptions import CalendarNotConfiguredError


def make_sync(**overrides):
    defaults = dict(
        task_id=1, provider_event_id="evt-1", sync_status=CalendarSyncStatus.SYNCED,
        sync_error=None, last_synced_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def connection_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def sync_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def task_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(connection_service, sync_service, task_service):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=42)
    app.dependency_overrides[get_calendar_connection_service] = lambda: connection_service
    app.dependency_overrides[get_calendar_sync_service] = lambda: sync_service
    app.dependency_overrides[get_task_service] = lambda: task_service
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def test_get_authorization_url_requires_authentication(connection_service):
    app.dependency_overrides[get_calendar_connection_service] = lambda: connection_service
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.get("/api/v1/calendar/authorize")

    test_client.close()
    app.dependency_overrides.clear()
    assert response.status_code == 401


def test_get_authorization_url_returns_the_url(client, connection_service):
    connection_service.get_authorization_url.return_value = "https://accounts.google.com/o/oauth2/v2/auth?..."

    response = client.get("/api/v1/calendar/authorize")

    assert response.status_code == 200
    assert response.json()["authorization_url"].startswith("https://accounts.google.com")


def test_get_authorization_url_not_configured_returns_503(client, connection_service):
    connection_service.get_authorization_url.side_effect = CalendarNotConfiguredError("no client id")

    response = client.get("/api/v1/calendar/authorize")

    assert response.status_code == 503


def test_connect_calendar_success_returns_204(client, connection_service):
    response = client.post("/api/v1/calendar/connect", json={"code": "auth-code"})

    assert response.status_code == 204
    connection_service.connect.assert_called_once_with(user_id=42, code="auth-code")


def test_disconnect_calendar_returns_204(client, connection_service):
    response = client.delete("/api/v1/calendar/disconnect")

    assert response.status_code == 204
    connection_service.disconnect.assert_called_once_with(user_id=42)


def test_get_calendar_status_reflects_the_service(client, connection_service):
    connection_service.is_connected.return_value = True

    response = client.get("/api/v1/calendar/status")

    assert response.status_code == 200
    assert response.json() == {"connected": True}


def test_sync_task_success_returns_the_sync_state(client, sync_service, task_service):
    task_service.get_task.return_value = SimpleNamespace(id=1)
    sync_service.sync_task.return_value = make_sync()

    response = client.post("/api/v1/tasks/1/calendar-sync")

    assert response.status_code == 200
    body = response.json()
    assert body["provider_event_id"] == "evt-1"
    assert body["sync_status"] == "SYNCED"


def test_sync_task_not_found_returns_404(client, task_service):
    task_service.get_task.side_effect = TaskNotFoundError("nope")

    response = client.post("/api/v1/tasks/1/calendar-sync")

    assert response.status_code == 404


def test_sync_task_not_connected_returns_404(client, task_service, sync_service):
    task_service.get_task.return_value = SimpleNamespace(id=1)
    sync_service.sync_task.side_effect = CalendarNotConnectedError("not connected")

    response = client.post("/api/v1/tasks/1/calendar-sync")

    assert response.status_code == 404


def test_unsync_task_returns_204(client, task_service, sync_service):
    task_service.get_task.return_value = SimpleNamespace(id=1)

    response = client.delete("/api/v1/tasks/1/calendar-sync")

    assert response.status_code == 204
    sync_service.unsync_task.assert_called_once()
