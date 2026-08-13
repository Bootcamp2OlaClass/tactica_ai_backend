from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.exceptions.degree import DegreeProgramNotFoundError
from app.main import app
from app.routers.degree import get_degree_progress_service, get_degree_recommendation_service
from app.services.degree_recommendation import NoDeclaredDegreeProgramError


def make_progress(**overrides):
    program = SimpleNamespace(id=1, name="BS Test Degree", institution_name="Test University")
    defaults = dict(
        degree_program=program,
        completed_course_codes={"TEST101"},
        completed_credits=3,
        unmet_requirements=[SimpleNamespace()],
        eligible_courses=[
            SimpleNamespace(course_code="TEST301", course_name="Testing Electives", credits=3, category="CS_ELECTIVE")
        ],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def progress_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(service, progress_service):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=42)
    app.dependency_overrides[get_degree_recommendation_service] = lambda: service
    app.dependency_overrides[get_degree_progress_service] = lambda: progress_service
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def test_get_degree_progress_requires_authentication(service):
    app.dependency_overrides[get_degree_recommendation_service] = lambda: service
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.get("/api/v1/degree-progress")

    test_client.close()
    app.dependency_overrides.clear()
    assert response.status_code == 401


def test_get_degree_progress_returns_progress_and_recommendations(client, service):
    service.recommend_next_courses.return_value = (make_progress(), [], None)

    response = client.get("/api/v1/degree-progress")

    assert response.status_code == 200
    body = response.json()
    assert body["degree_program_name"] == "BS Test Degree"
    assert body["completed_credits"] == 3
    assert body["eligible_courses"][0]["course_code"] == "TEST301"
    service.recommend_next_courses.assert_called_once_with(user_id=42)


def test_get_degree_progress_returns_404_when_not_declared(client, service):
    service.recommend_next_courses.side_effect = NoDeclaredDegreeProgramError("none")

    response = client.get("/api/v1/degree-progress")

    assert response.status_code == 404


def test_declare_degree_program_requires_authentication():
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.post("/api/v1/degree-progress/declare", json={"degree_program_id": 1})

    test_client.close()
    assert response.status_code == 401


def test_declare_degree_program_success_returns_204(client, progress_service):
    response = client.post("/api/v1/degree-progress/declare", json={"degree_program_id": 1})

    assert response.status_code == 204
    progress_service.declare_program.assert_called_once_with(user_id=42, degree_program_id=1)


def test_declare_degree_program_not_found_returns_404(client, progress_service):
    progress_service.declare_program.side_effect = DegreeProgramNotFoundError("not found")

    response = client.post("/api/v1/degree-progress/declare", json={"degree_program_id": 999999})

    assert response.status_code == 404
