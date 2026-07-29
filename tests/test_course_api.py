from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.exceptions.course import CourseConflictError, CourseNotFoundError
from app.main import app
from app.models.course import CourseStatus
from app.routers.courses import get_course_service
from app.services.course import CourseService


def make_course(**overrides):
    data = {
        "id": 11,
        "semester_id": 7,
        "course_code": "CS101",
        "name": "Introduction to Computer Science",
        "instructor_name": "Ada Lovelace",
        "credits": 3,
        "classroom": "Room 101",
        "color": "#123ABC",
        "description": "Foundational concepts.",
        "status": CourseStatus.ACTIVE,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def paginated(items=None, **overrides):
    data = {
        "items": items or [],
        "page": 1,
        "page_size": 20,
        "total": len(items or []),
        "total_pages": 1 if items else 0,
    }
    data.update(overrides)
    return data


@pytest.fixture
def service():
    return MagicMock(spec=CourseService)


@pytest.fixture
def client(service):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=42)
    app.dependency_overrides[get_course_service] = lambda: service
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def test_course_endpoints_require_authentication(service):
    app.dependency_overrides[get_course_service] = lambda: service
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.get("/api/v1/courses")

    test_client.close()
    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "detail" in response.json()
    service.list_courses.assert_not_called()


def test_create_nested_course_returns_201_and_uses_path_semester(client, service):
    service.create_course.return_value = make_course()

    response = client.post(
        "/api/v1/semesters/7/courses",
        json={
            "course_code": " cs101 ",
            "name": "Intro to CS",
            "credits": 3,
        },
    )

    assert response.status_code == 201
    assert response.json()["course_code"] == "CS101"

    call = service.create_course.call_args.kwargs
    assert call["user_id"] == 42
    assert call["course_data"].semester_id == 7
    assert call["course_data"].course_code == "CS101"


def test_create_duplicate_course_returns_shared_409_error(client, service):
    service.create_course.side_effect = CourseConflictError(
        "An active course with the same code already exists in this semester."
    )

    response = client.post(
        "/api/v1/semesters/7/courses",
        json={
            "course_code": "CS101",
            "name": "Intro to CS",
            "credits": 3,
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "An active course with the same code already exists in this semester."
    }


def test_unowned_semester_is_reported_as_not_found(client, service):
    service.list_courses.side_effect = CourseNotFoundError("Semester not found.")

    response = client.get("/api/v1/semesters/99/courses")

    assert response.status_code == 404
    assert response.json() == {"detail": "Semester not found."}


def test_nested_course_list_supports_pagination(client, service):
    service.list_courses.return_value = paginated(
        [make_course()],
        page=2,
        page_size=5,
        total=6,
        total_pages=2,
    )

    response = client.get(
        "/api/v1/semesters/7/courses",
        params={"page": 2, "page_size": 5},
    )

    assert response.status_code == 200
    assert response.json()["total_pages"] == 2
    service.list_courses.assert_called_once_with(
        user_id=42,
        semester_id=7,
        page=2,
        page_size=5,
    )


def test_global_course_list_forwards_filters_and_sorting(client, service):
    service.list_courses.return_value = paginated([make_course()])

    response = client.get(
        "/api/v1/courses",
        params={
            "semester_id": 7,
            "status": "ACTIVE",
            "search": "computer",
            "page": 1,
            "page_size": 20,
            "sort_by": "name",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 200
    service.list_courses.assert_called_once_with(
        user_id=42,
        semester_id=7,
        status=CourseStatus.ACTIVE,
        search="computer",
        page=1,
        page_size=20,
        sort_by="name",
        sort_order="asc",
    )


def test_course_detail_update_and_delete_delegate_with_owner_scope(client, service):
    existing = make_course()
    updated = make_course(name="Advanced Computer Science")
    service.get_course.return_value = existing
    service.update_course.return_value = updated
    service.delete_course.return_value = updated

    detail_response = client.get("/api/v1/courses/11")
    update_response = client.patch(
        "/api/v1/courses/11",
        json={"name": "Advanced Computer Science"},
    )
    delete_response = client.delete("/api/v1/courses/11")

    assert detail_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Advanced Computer Science"
    assert delete_response.status_code == 204
    assert delete_response.content == b""

    service.get_course.assert_called_once_with(course_id=11, user_id=42)
    update_call = service.update_course.call_args.kwargs
    assert update_call["course_id"] == 11
    assert update_call["user_id"] == 42
    assert update_call["course_data"].model_dump(exclude_unset=True) == {
        "name": "Advanced Computer Science"
    }
    service.delete_course.assert_called_once_with(course_id=11, user_id=42)


def test_openapi_documents_nested_and_global_authenticated_course_routes():
    schema = app.openapi()
    expected_operations = {
        ("/api/v1/semesters/{semester_id}/courses", "post"),
        ("/api/v1/semesters/{semester_id}/courses", "get"),
        ("/api/v1/courses", "get"),
        ("/api/v1/courses/{course_id}", "get"),
        ("/api/v1/courses/{course_id}", "patch"),
        ("/api/v1/courses/{course_id}", "delete"),
    }

    for path, method in expected_operations:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]

    create_schema = schema["paths"][
        "/api/v1/semesters/{semester_id}/courses"
    ]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert create_schema["$ref"].endswith("/CourseCreateRequest")
