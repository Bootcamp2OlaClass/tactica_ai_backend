from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.exceptions.course import (
    CourseConflictError,
    CourseNotFoundError,
    CourseValidationError,
)
from app.models.course import CourseStatus
from app.schemas.course import CourseCreate, CourseUpdate
from app.services.course import CourseService


def make_course(**overrides):
    data = {
        "id": 1,
        "semester_id": 10,
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
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_semester(**overrides):
    data = {
        "id": 10,
        "user_id": 1,
        "is_deleted": False,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_create_data(**overrides):
    data = {
        "semester_id": 10,
        "course_code": "CS101",
        "name": "Introduction to Computer Science",
        "credits": 3,
        "status": CourseStatus.ACTIVE,
    }
    data.update(overrides)
    return CourseCreate(**data)


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def semester_repository():
    return MagicMock()


@pytest.fixture
def service(db, semester_repository):
    return CourseService(
        db=db,
        semester_repository=semester_repository,
    )


def test_create_course_validates_parent_semester(
    service,
    semester_repository,
):
    semester_repository.get_by_id_and_owner.return_value = None

    with pytest.raises(
        CourseNotFoundError,
        match="Semester not found",
    ):
        service.create_course(
            user_id=1,
            course_data=make_create_data(),
        )

    semester_repository.get_by_id_and_owner.assert_called_once_with(
        semester_id=10,
        user_id=1,
    )


def test_create_course_rejects_duplicate_active_code(
    service,
    semester_repository,
    monkeypatch,
):
    semester_repository.get_by_id_and_owner.return_value = (
        make_semester()
    )

    duplicate_course = make_course()

    duplicate_mock = MagicMock(
        return_value=duplicate_course
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.find_duplicate_course_code",
        duplicate_mock,
    )

    create_mock = MagicMock()

    monkeypatch.setattr(
        "app.services.course.course_repository.create_course",
        create_mock,
    )

    with pytest.raises(
        CourseConflictError,
        match="same code",
    ):
        service.create_course(
            user_id=1,
            course_data=make_create_data(
                course_code=" cs101 ",
            ),
        )

    duplicate_mock.assert_called_once_with(
        db=service.db,
        semester_id=10,
        course_code="CS101",
        user_id=1,
    )

    create_mock.assert_not_called()


def test_create_course_uses_normalized_code(
    service,
    semester_repository,
    monkeypatch,
):
    semester_repository.get_by_id_and_owner.return_value = (
        make_semester()
    )

    duplicate_mock = MagicMock(return_value=None)

    created_course = make_course(
        course_code="CS101"
    )

    create_mock = MagicMock(
        return_value=created_course
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.find_duplicate_course_code",
        duplicate_mock,
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.create_course",
        create_mock,
    )

    result = service.create_course(
        user_id=1,
        course_data=make_create_data(
            course_code=" cs101 ",
        ),
    )

    assert result is created_course

    duplicate_mock.assert_called_once_with(
        db=service.db,
        semester_id=10,
        course_code="CS101",
        user_id=1,
    )

    payload = create_mock.call_args.kwargs["course_data"]

    assert payload["course_code"] == "CS101"
    assert payload["semester_id"] == 10
    assert payload["status"] is CourseStatus.ACTIVE


def test_create_non_active_course_skips_duplicate_check(
    service,
    semester_repository,
    monkeypatch,
):
    semester_repository.get_by_id_and_owner.return_value = (
        make_semester()
    )

    duplicate_mock = MagicMock()

    created_course = make_course(
        status=CourseStatus.COMPLETED,
    )

    create_mock = MagicMock(
        return_value=created_course
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.find_duplicate_course_code",
        duplicate_mock,
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.create_course",
        create_mock,
    )

    result = service.create_course(
        user_id=1,
        course_data=make_create_data(
            status=CourseStatus.COMPLETED,
        ),
    )

    assert result is created_course
    duplicate_mock.assert_not_called()
    create_mock.assert_called_once()


def test_create_course_maps_integrity_error_to_conflict(
    service,
    semester_repository,
    monkeypatch,
):
    semester_repository.get_by_id_and_owner.return_value = (
        make_semester()
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.find_duplicate_course_code",
        MagicMock(return_value=None),
    )

    statement = "INSERT INTO courses"
    parameters = {}
    original_error = Exception("duplicate")

    create_mock = MagicMock(
        side_effect=IntegrityError(
            statement,
            parameters,
            original_error,
        )
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.create_course",
        create_mock,
    )

    with pytest.raises(CourseConflictError):
        service.create_course(
            user_id=1,
            course_data=make_create_data(),
        )

    service.db.rollback.assert_called_once()


def test_get_course_returns_owned_course(
    service,
    monkeypatch,
):
    course = make_course()

    get_mock = MagicMock(return_value=course)

    monkeypatch.setattr(
        "app.services.course.course_repository.get_course_by_id",
        get_mock,
    )

    result = service.get_course(
        course_id=1,
        user_id=1,
    )

    assert result is course

    get_mock.assert_called_once_with(
        db=service.db,
        course_id=1,
        user_id=1,
    )


def test_get_course_treats_inaccessible_course_as_not_found(
    service,
    monkeypatch,
):
    get_mock = MagicMock(return_value=None)

    monkeypatch.setattr(
        "app.services.course.course_repository.get_course_by_id",
        get_mock,
    )

    with pytest.raises(
        CourseNotFoundError,
        match="Course not found",
    ):
        service.get_course(
            course_id=1,
            user_id=99,
        )


@pytest.mark.parametrize(
    ("page", "page_size"),
    [
        (0, 20),
        (1, 0),
    ],
)
def test_list_courses_rejects_invalid_pagination(
    service,
    page,
    page_size,
):
    with pytest.raises(CourseValidationError):
        service.list_courses(
            user_id=1,
            page=page,
            page_size=page_size,
        )


def test_list_courses_validates_filtered_semester(
    service,
    semester_repository,
):
    semester_repository.get_by_id_and_owner.return_value = None

    with pytest.raises(CourseNotFoundError):
        service.list_courses(
            user_id=1,
            semester_id=10,
        )

    semester_repository.get_by_id_and_owner.assert_called_once_with(
        semester_id=10,
        user_id=1,
    )


def test_list_courses_returns_pagination_metadata(
    service,
    monkeypatch,
):
    courses = [
        make_course(id=1),
        make_course(id=2),
    ]

    list_mock = MagicMock(return_value=courses)
    count_mock = MagicMock(return_value=41)

    monkeypatch.setattr(
        "app.services.course.course_repository.list_courses_by_user",
        list_mock,
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.count_courses",
        count_mock,
    )

    result = service.list_courses(
        user_id=1,
        page=2,
        page_size=20,
        search="CS",
        status=CourseStatus.ACTIVE,
        sort_by="name",
        sort_order="asc",
    )

    assert result == {
        "items": courses,
        "page": 2,
        "page_size": 20,
        "total": 41,
        "total_pages": 3,
    }

    list_mock.assert_called_once_with(
        db=service.db,
        user_id=1,
        offset=20,
        limit=20,
        search="CS",
        semester_id=None,
        status=CourseStatus.ACTIVE,
        sort_by="name",
        sort_order="asc",
    )

    count_mock.assert_called_once_with(
        db=service.db,
        user_id=1,
        search="CS",
        semester_id=None,
        status=CourseStatus.ACTIVE,
    )


def test_update_unrelated_field_skips_duplicate_check(
    service,
    monkeypatch,
):
    course = make_course()

    get_mock = MagicMock(return_value=course)
    duplicate_mock = MagicMock()
    update_mock = MagicMock(return_value=course)

    monkeypatch.setattr(
        "app.services.course.course_repository.get_course_by_id",
        get_mock,
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.find_duplicate_course_code",
        duplicate_mock,
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.update_course",
        update_mock,
    )

    result = service.update_course(
        course_id=1,
        user_id=1,
        course_data=CourseUpdate(
            name="Updated Course Name"
        ),
    )

    assert result is course
    duplicate_mock.assert_not_called()

    update_mock.assert_called_once_with(
        db=service.db,
        course=course,
        update_data={
            "name": "Updated Course Name"
        },
    )


def test_update_course_code_checks_duplicate(
    service,
    monkeypatch,
):
    course = make_course()

    monkeypatch.setattr(
        "app.services.course.course_repository.get_course_by_id",
        MagicMock(return_value=course),
    )

    duplicate_mock = MagicMock(
        return_value=make_course(id=2)
    )

    update_mock = MagicMock()

    monkeypatch.setattr(
        "app.services.course.course_repository.find_duplicate_course_code",
        duplicate_mock,
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.update_course",
        update_mock,
    )

    with pytest.raises(CourseConflictError):
        service.update_course(
            course_id=1,
            user_id=1,
            course_data=CourseUpdate(
                course_code=" cs202 "
            ),
        )

    duplicate_mock.assert_called_once_with(
        db=service.db,
        semester_id=10,
        course_code="CS202",
        user_id=1,
        exclude_course_id=1,
    )

    update_mock.assert_not_called()


def test_update_course_code_succeeds_without_duplicate(
    service,
    monkeypatch,
):
    course = make_course()

    monkeypatch.setattr(
        "app.services.course.course_repository.get_course_by_id",
        MagicMock(return_value=course),
    )

    duplicate_mock = MagicMock(return_value=None)
    update_mock = MagicMock(return_value=course)

    monkeypatch.setattr(
        "app.services.course.course_repository.find_duplicate_course_code",
        duplicate_mock,
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.update_course",
        update_mock,
    )

    result = service.update_course(
        course_id=1,
        user_id=1,
        course_data=CourseUpdate(
            course_code=" cs202 "
        ),
    )

    assert result is course

    update_mock.assert_called_once_with(
        db=service.db,
        course=course,
        update_data={
            "course_code": "CS202"
        },
    )


def test_update_course_validates_new_semester(
    service,
    semester_repository,
    monkeypatch,
):
    course = make_course()

    monkeypatch.setattr(
        "app.services.course.course_repository.get_course_by_id",
        MagicMock(return_value=course),
    )

    semester_repository.get_by_id_and_owner.return_value = None

    with pytest.raises(CourseNotFoundError):
        service.update_course(
            course_id=1,
            user_id=1,
            course_data=CourseUpdate(
                semester_id=20
            ),
        )

    semester_repository.get_by_id_and_owner.assert_called_once_with(
        semester_id=20,
        user_id=1,
    )


def test_update_empty_payload_returns_existing_course(
    service,
    monkeypatch,
):
    course = make_course()

    monkeypatch.setattr(
        "app.services.course.course_repository.get_course_by_id",
        MagicMock(return_value=course),
    )

    update_mock = MagicMock()

    monkeypatch.setattr(
        "app.services.course.course_repository.update_course",
        update_mock,
    )

    result = service.update_course(
        course_id=1,
        user_id=1,
        course_data=CourseUpdate(),
    )

    assert result is course
    update_mock.assert_not_called()


def test_delete_course_soft_deletes_owned_course(
    service,
    monkeypatch,
):
    course = make_course()

    get_mock = MagicMock(return_value=course)
    delete_mock = MagicMock(return_value=course)

    monkeypatch.setattr(
        "app.services.course.course_repository.get_course_by_id",
        get_mock,
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.soft_delete_course",
        delete_mock,
    )

    result = service.delete_course(
        course_id=1,
        user_id=1,
    )

    assert result is course

    get_mock.assert_called_once_with(
        db=service.db,
        course_id=1,
        user_id=1,
    )

    delete_mock.assert_called_once_with(
        db=service.db,
        course=course,
    )


def test_delete_inaccessible_course_raises_not_found(
    service,
    monkeypatch,
):
    get_mock = MagicMock(return_value=None)
    delete_mock = MagicMock()

    monkeypatch.setattr(
        "app.services.course.course_repository.get_course_by_id",
        get_mock,
    )

    monkeypatch.setattr(
        "app.services.course.course_repository.soft_delete_course",
        delete_mock,
    )

    with pytest.raises(CourseNotFoundError):
        service.delete_course(
            course_id=1,
            user_id=99,
        )

    delete_mock.assert_not_called()