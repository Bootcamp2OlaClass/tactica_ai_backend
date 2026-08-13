from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.main import app
from app.models.notification import NotificationType
from app.routers.notification import get_notification_service


@pytest.fixture
def service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(service):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=42)
    app.dependency_overrides[get_notification_service] = lambda: service
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def test_get_preferences_requires_authentication(service):
    app.dependency_overrides[get_notification_service] = lambda: service
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.get("/api/v1/notification-preferences")

    test_client.close()
    app.dependency_overrides.clear()
    assert response.status_code == 401


def test_get_preferences_returns_all_types(client, service):
    service.list_preferences.return_value = {t: True for t in NotificationType}

    response = client.get("/api/v1/notification-preferences")

    assert response.status_code == 200
    body = response.json()["preferences"]
    assert set(body.keys()) == {t.value for t in NotificationType}
    service.list_preferences.assert_called_once_with(user_id=42)


def test_update_preference_sets_and_returns_all(client, service):
    service.list_preferences.return_value = {
        t: (t != NotificationType.ASSIGNMENT_DUE) for t in NotificationType
    }

    response = client.put(
        "/api/v1/notification-preferences/ASSIGNMENT_DUE", json={"enabled": False}
    )

    assert response.status_code == 200
    service.set_preference.assert_called_once_with(
        user_id=42, notification_type=NotificationType.ASSIGNMENT_DUE, enabled=False
    )
    assert response.json()["preferences"]["ASSIGNMENT_DUE"] is False
