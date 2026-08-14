"""Tests for PATCH /auth/me (Settings -> Profile). Follows the same
TestClient-against-a-real-db_session pattern as tests/test_auth_hardening.py."""

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.routers.auth import login_rate_limit, register_rate_limit


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    def _no_rate_limit():
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[register_rate_limit] = _no_rate_limit
    app.dependency_overrides[login_rate_limit] = _no_rate_limit
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def _register_and_get_token(client, email="profile@example.com"):
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "Sup3rSecret!", "full_name": "Original Name"},
    )
    return response.json()["access_token"]


def test_update_me_requires_authentication(client):
    response = client.patch("/auth/me", json={"full_name": "New Name"})

    assert response.status_code == 401


def test_update_me_updates_full_name(client):
    token = _register_and_get_token(client)

    response = client.patch(
        "/auth/me",
        json={"full_name": "Updated Name"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Updated Name"

    follow_up = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert follow_up.json()["full_name"] == "Updated Name"


def test_update_me_strips_whitespace(client):
    token = _register_and_get_token(client, email="profile-strip@example.com")

    response = client.patch(
        "/auth/me",
        json={"full_name": "  Spaced Name  "},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Spaced Name"


def test_update_me_rejects_blank_name(client):
    token = _register_and_get_token(client, email="profile-blank@example.com")

    response = client.patch(
        "/auth/me",
        json={"full_name": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_update_me_does_not_change_email_or_role(client):
    token = _register_and_get_token(client, email="profile-immutable@example.com")

    response = client.patch(
        "/auth/me",
        json={"full_name": "Someone Else"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "profile-immutable@example.com"
    assert body["role"] == "STUDENT"
