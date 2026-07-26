from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.course import CourseStatus
from app.schemas.course import (
    COURSE_DESCRIPTION_MAX_LENGTH,
    CourseCreate,
    CourseListResponse,
    CourseResponse,
    CourseUpdate,
)


def valid_course_data(**overrides):
    data = {
        "semester_id": 1,
        "course_code": "CS101",
        "name": "Introduction to Computer Science",
        "credits": 3,
    }
    data.update(overrides)
    return data


def course_object(**overrides):
    data = {
        "id": 1,
        "semester_id": 2,
        "course_code": "CS101",
        "name": "Introduction to Computer Science",
        "instructor_name": "Ada Lovelace",
        "credits": 3,
        "classroom": "Room 101",
        "color": "#123ABC",
        "description": "Foundational concepts.",
        "status": CourseStatus.ACTIVE,
        "is_deleted": False,
        "deleted_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_course_create_validates_and_normalizes_required_fields():
    course = CourseCreate(
        **valid_course_data(
            course_code=" cs101 ",
            name=" Intro to CS ",
        )
    )

    assert course.course_code == "CS101"
    assert course.name == "Intro to CS"
    assert course.status is CourseStatus.ACTIVE


@pytest.mark.parametrize("course_code", ["", "   "])
def test_course_create_rejects_blank_course_codes(course_code):
    with pytest.raises(ValidationError):
        CourseCreate(**valid_course_data(course_code=course_code))


def test_course_create_rejects_blank_course_name_and_trims_name():
    with pytest.raises(ValidationError):
        CourseCreate(**valid_course_data(name="   "))

    course = CourseCreate(**valid_course_data(name=" Course Name "))

    assert course.name == "Course Name"


@pytest.mark.parametrize("credits", [0, 20])
def test_course_create_accepts_credit_boundaries(credits):
    assert CourseCreate(**valid_course_data(credits=credits)).credits == credits


@pytest.mark.parametrize("credits", [-1, 21])
def test_course_create_rejects_unsupported_credits(credits):
    with pytest.raises(ValidationError):
        CourseCreate(**valid_course_data(credits=credits))


def test_course_create_validates_color_and_status():
    course = CourseCreate(**valid_course_data(color="#A1B2C3", status="completed"))

    assert course.color == "#A1B2C3"
    assert course.status is CourseStatus.COMPLETED

    for color in ("123456", "#123", "#1234567", "#GGGGGG"):
        with pytest.raises(ValidationError):
            CourseCreate(**valid_course_data(color=color))

    with pytest.raises(ValidationError):
        CourseCreate(**valid_course_data(status="invalid"))


def test_course_update_supports_true_partial_updates():
    update = CourseUpdate(name=" Updated Name ")

    assert update.name == "Updated Name"
    assert update.model_fields_set == {"name"}
    assert CourseUpdate().model_dump(exclude_unset=True) == {}
    assert CourseUpdate(semester_id=3).semester_id == 3


def test_course_update_normalizes_course_code():
    update = CourseUpdate(course_code=" cs202 ")

    assert update.course_code == "CS202"
    assert update.model_dump(exclude_unset=True) == {"course_code": "CS202"}


def test_course_create_rejects_database_managed_fields():
    with pytest.raises(ValidationError):
        CourseCreate(**valid_course_data(id=1))


def test_course_response_serializes_orm_like_object_without_deletion_fields():
    response = CourseResponse.model_validate(course_object())

    assert response.semester_id == 2
    assert "is_deleted" not in response.model_dump()
    assert "deleted_at" not in response.model_dump()


def test_course_list_response_serializes_items_and_pagination_metadata():
    response = CourseListResponse(
        items=[
            CourseResponse.model_validate(course_object(id=1)),
            CourseResponse.model_validate(course_object(id=2)),
        ],
        page=1,
        page_size=20,
        total=2,
        total_pages=1,
    )

    assert [course.id for course in response.items] == [1, 2]
    assert response.model_dump(exclude={"items"}) == {
        "page": 1,
        "page_size": 20,
        "total": 2,
        "total_pages": 1,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [("page", 0), ("page_size", 0), ("total", -1), ("total_pages", -1)],
)
def test_course_list_response_rejects_invalid_pagination(field, value):
    data = {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
        "total_pages": 0,
    }
    data[field] = value

    with pytest.raises(ValidationError):
        CourseListResponse(**data)


def test_course_create_accepts_description_at_max_length():
    course = CourseCreate(
        **valid_course_data(description="a" * COURSE_DESCRIPTION_MAX_LENGTH)
    )

    assert len(course.description) == COURSE_DESCRIPTION_MAX_LENGTH


def test_course_create_rejects_overlong_description():
    with pytest.raises(ValidationError):
        CourseCreate(
            **valid_course_data(
                description="a" * (COURSE_DESCRIPTION_MAX_LENGTH + 1)
            )
        )
