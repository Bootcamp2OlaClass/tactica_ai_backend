from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.exceptions.semester import (
    SemesterConflictError,
    SemesterNotFoundError,
    SemesterValidationError,
)
from app.models.semester import Semester, SemesterStatus
from app.schemas.semester import SemesterCreate, SemesterUpdate
from app.services.semester import SemesterService


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_repository() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(
    mock_db: MagicMock,
    mock_repository: MagicMock,
) -> SemesterService:
    return SemesterService(
        db=mock_db,
        repository=mock_repository,
    )


@pytest.fixture
def existing_semester() -> Semester:
    return Semester(
        id=1,
        user_id=10,
        name="Fall Semester",
        academic_year=2026,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 12, 20),
        status=SemesterStatus.ACTIVE,
        description="Current semester",
        is_deleted=False,
    )


@pytest.fixture
def create_data() -> SemesterCreate:
    return SemesterCreate(
        name="Fall Semester",
        academic_year=2026,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 12, 20),
        status=SemesterStatus.ACTIVE,
        description="Current semester",
    )


# ---------------------------------------------------------------------------
# Create semester
# ---------------------------------------------------------------------------


def test_create_semester_success(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    create_data: SemesterCreate,
    existing_semester: Semester,
) -> None:
    mock_repository.find_duplicate.return_value = None
    mock_repository.create.return_value = existing_semester

    result = service.create_semester(
        user_id=10,
        semester_data=create_data,
    )

    assert result is existing_semester

    mock_repository.find_duplicate.assert_called_once_with(
        user_id=10,
        name="Fall Semester",
        academic_year=2026,
        status=SemesterStatus.ACTIVE,
    )

    created_semester = mock_repository.create.call_args.args[0]

    assert created_semester.user_id == 10
    assert created_semester.name == "Fall Semester"
    assert created_semester.academic_year == 2026
    assert created_semester.start_date == date(2026, 8, 1)
    assert created_semester.end_date == date(2026, 12, 20)
    assert created_semester.status == SemesterStatus.ACTIVE
    assert created_semester.description == "Current semester"

    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()


def test_create_duplicate_active_semester_raises_error(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    create_data: SemesterCreate,
    existing_semester: Semester,
) -> None:
    mock_repository.find_duplicate.return_value = existing_semester

    with pytest.raises(
        SemesterConflictError,
        match="An active semester with the same name",
    ):
        service.create_semester(
            user_id=10,
            semester_data=create_data,
        )

    mock_repository.create.assert_not_called()
    mock_db.commit.assert_not_called()


def test_another_user_can_create_identical_semester(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    create_data: SemesterCreate,
) -> None:
    created_semester = Semester(
        id=2,
        user_id=20,
        name=create_data.name,
        academic_year=create_data.academic_year,
        start_date=create_data.start_date,
        end_date=create_data.end_date,
        status=create_data.status,
        description=create_data.description,
    )

    # Repository searches duplicates within user_id=20 only.
    mock_repository.find_duplicate.return_value = None
    mock_repository.create.return_value = created_semester

    result = service.create_semester(
        user_id=20,
        semester_data=create_data,
    )

    assert result.user_id == 20

    mock_repository.find_duplicate.assert_called_once_with(
        user_id=20,
        name="Fall Semester",
        academic_year=2026,
        status=SemesterStatus.ACTIVE,
    )

    mock_db.commit.assert_called_once()


def test_create_non_active_semester_does_not_check_duplicate(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
) -> None:
    semester_data = SemesterCreate(
        name="Spring Semester",
        academic_year=2026,
        start_date=date(2027, 1, 10),
        end_date=date(2027, 5, 20),
        status=SemesterStatus.UPCOMING,
        description=None,
    )

    created_semester = Semester(
        id=2,
        user_id=10,
        **semester_data.model_dump(),
    )

    mock_repository.create.return_value = created_semester

    result = service.create_semester(
        user_id=10,
        semester_data=semester_data,
    )

    assert result is created_semester
    mock_repository.find_duplicate.assert_not_called()
    mock_db.commit.assert_called_once()


def test_create_semester_with_invalid_date_range_raises_error(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
) -> None:
    # Construct bypasses Pydantic validation so service validation
    # can be tested independently.
    invalid_data = SemesterCreate.model_construct(
        name="Invalid Semester",
        academic_year=2026,
        start_date=date(2026, 12, 20),
        end_date=date(2026, 8, 1),
        status=SemesterStatus.ACTIVE,
        description=None,
    )

    with pytest.raises(
        SemesterValidationError,
        match="start_date must be earlier than end_date",
    ):
        service.create_semester(
            user_id=10,
            semester_data=invalid_data,
        )

    mock_repository.find_duplicate.assert_not_called()
    mock_repository.create.assert_not_called()
    mock_db.commit.assert_not_called()


def test_create_semester_rolls_back_on_database_error(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    create_data: SemesterCreate,
) -> None:
    mock_repository.find_duplicate.return_value = None
    mock_repository.create.side_effect = SQLAlchemyError(
        "Database error"
    )

    with pytest.raises(SQLAlchemyError):
        service.create_semester(
            user_id=10,
            semester_data=create_data,
        )

    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_called_once()


def test_create_translates_integrity_race_to_conflict(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    create_data: SemesterCreate,
) -> None:
    mock_repository.find_duplicate.return_value = None
    mock_repository.create.side_effect = IntegrityError(
        "insert",
        {},
        Exception("duplicate"),
    )

    with pytest.raises(SemesterConflictError):
        service.create_semester(
            user_id=10,
            semester_data=create_data,
        )

    mock_db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Get semester
# ---------------------------------------------------------------------------


def test_get_semester_success(
    service: SemesterService,
    mock_repository: MagicMock,
    existing_semester: Semester,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )

    result = service.get_semester(
        semester_id=1,
        user_id=10,
    )

    assert result is existing_semester

    mock_repository.get_by_id_and_owner.assert_called_once_with(
        semester_id=1,
        user_id=10,
    )


def test_get_missing_semester_raises_not_found(
    service: SemesterService,
    mock_repository: MagicMock,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = None

    with pytest.raises(
        SemesterNotFoundError,
        match="Semester not found",
    ):
        service.get_semester(
            semester_id=999,
            user_id=10,
        )


def test_user_cannot_get_another_users_semester(
    service: SemesterService,
    mock_repository: MagicMock,
) -> None:
    # Ownership-scoped repository returns None when the record
    # belongs to another user.
    mock_repository.get_by_id_and_owner.return_value = None

    with pytest.raises(
        SemesterNotFoundError,
        match="Semester not found",
    ):
        service.get_semester(
            semester_id=1,
            user_id=20,
        )

    mock_repository.get_by_id_and_owner.assert_called_once_with(
        semester_id=1,
        user_id=20,
    )


def test_deleted_semester_cannot_be_retrieved(
    service: SemesterService,
    mock_repository: MagicMock,
) -> None:
    # Repository excludes soft-deleted semesters.
    mock_repository.get_by_id_and_owner.return_value = None

    with pytest.raises(
        SemesterNotFoundError,
        match="Semester not found",
    ):
        service.get_semester(
            semester_id=1,
            user_id=10,
        )


# ---------------------------------------------------------------------------
# List semesters
# ---------------------------------------------------------------------------


def test_list_semesters_success(
    service: SemesterService,
    mock_repository: MagicMock,
    existing_semester: Semester,
) -> None:
    mock_repository.list_by_user.return_value = [
        existing_semester
    ]
    mock_repository.count_by_user.return_value = 41

    result = service.list_semesters(
        user_id=10,
        page=2,
        page_size=20,
        search="Fall",
        status=SemesterStatus.ACTIVE,
        sort_by="name",
        sort_order="asc",
    )

    assert result == {
        "items": [existing_semester],
        "total": 41,
        "page": 2,
        "page_size": 20,
        "total_pages": 3,
    }

    mock_repository.list_by_user.assert_called_once_with(
        user_id=10,
        page=2,
        page_size=20,
        search="Fall",
        status=SemesterStatus.ACTIVE,
        sort_by="name",
        sort_order="asc",
    )

    mock_repository.count_by_user.assert_called_once_with(
        user_id=10,
        search="Fall",
        status=SemesterStatus.ACTIVE,
    )


def test_list_semesters_returns_zero_total_pages_when_empty(
    service: SemesterService,
    mock_repository: MagicMock,
) -> None:
    mock_repository.list_by_user.return_value = []
    mock_repository.count_by_user.return_value = 0

    result = service.list_semesters(user_id=10)

    assert result["items"] == []
    assert result["total"] == 0
    assert result["total_pages"] == 0


@pytest.mark.parametrize(
    ("page", "page_size", "message"),
    [
        (0, 20, "Page must be greater than or equal to 1"),
        (1, 0, "Page size must be greater than or equal to 1"),
    ],
)
def test_list_semesters_rejects_invalid_pagination(
    service: SemesterService,
    mock_repository: MagicMock,
    page: int,
    page_size: int,
    message: str,
) -> None:
    with pytest.raises(SemesterValidationError, match=message):
        service.list_semesters(
            user_id=10,
            page=page,
            page_size=page_size,
        )

    mock_repository.list_by_user.assert_not_called()
    mock_repository.count_by_user.assert_not_called()


# ---------------------------------------------------------------------------
# Update semester
# ---------------------------------------------------------------------------


def test_partial_update_preserves_omitted_fields(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    existing_semester: Semester,
) -> None:
    update_data = SemesterUpdate(
        description="Updated description",
    )

    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )
    mock_repository.update.return_value = existing_semester

    result = service.update_semester(
        semester_id=1,
        user_id=10,
        semester_data=update_data,
    )

    assert result is existing_semester

    mock_repository.update.assert_called_once_with(
        semester=existing_semester,
        update_data={
            "description": "Updated description",
        },
    )

    mock_repository.find_duplicate.assert_not_called()
    mock_db.commit.assert_called_once()


def test_update_only_start_date_validates_existing_end_date(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    existing_semester: Semester,
) -> None:
    update_data = SemesterUpdate(
        start_date=date(2026, 12, 21),
    )

    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )

    with pytest.raises(
        SemesterValidationError,
        match="start_date must be earlier than end_date",
    ):
        service.update_semester(
            semester_id=1,
            user_id=10,
            semester_data=update_data,
        )

    mock_repository.update.assert_not_called()
    mock_db.commit.assert_not_called()


def test_update_only_end_date_validates_existing_start_date(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    existing_semester: Semester,
) -> None:
    update_data = SemesterUpdate(
        end_date=date(2026, 7, 31),
    )

    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )

    with pytest.raises(
        SemesterValidationError,
        match="start_date must be earlier than end_date",
    ):
        service.update_semester(
            semester_id=1,
            user_id=10,
            semester_data=update_data,
        )

    mock_repository.update.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("name", "Updated Semester"),
        ("academic_year", 2027),
    ],
)
def test_update_name_or_academic_year_checks_duplicate(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    existing_semester: Semester,
    field_name: str,
    field_value: str | int,
) -> None:
    update_data = SemesterUpdate(
        **{field_name: field_value}
    )

    duplicate_semester = Semester(
        id=2,
        user_id=10,
        name="Updated Semester",
        academic_year=2027,
        start_date=date(2027, 1, 1),
        end_date=date(2027, 5, 1),
        status=SemesterStatus.ACTIVE,
    )

    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )
    mock_repository.find_duplicate.return_value = (
        duplicate_semester
    )

    with pytest.raises(
        SemesterConflictError,
        match="An active semester with the same name",
    ):
        service.update_semester(
            semester_id=1,
            user_id=10,
            semester_data=update_data,
        )

    mock_repository.find_duplicate.assert_called_once()
    mock_repository.update.assert_not_called()
    mock_db.commit.assert_not_called()


def test_changing_status_to_active_checks_duplicate(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    existing_semester: Semester,
) -> None:
    existing_semester.status = SemesterStatus.UPCOMING

    update_data = SemesterUpdate(
        status=SemesterStatus.ACTIVE,
    )

    duplicate_semester = Semester(
        id=2,
        user_id=10,
        name=existing_semester.name,
        academic_year=existing_semester.academic_year,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 12, 20),
        status=SemesterStatus.ACTIVE,
    )

    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )
    mock_repository.find_duplicate.return_value = (
        duplicate_semester
    )

    with pytest.raises(
        SemesterConflictError,
        match="An active semester with the same name",
    ):
        service.update_semester(
            semester_id=1,
            user_id=10,
            semester_data=update_data,
        )

    mock_repository.find_duplicate.assert_called_once_with(
        user_id=10,
        name=existing_semester.name,
        academic_year=existing_semester.academic_year,
        status=SemesterStatus.ACTIVE,
        exclude_semester_id=existing_semester.id,
    )

    mock_repository.update.assert_not_called()
    mock_db.commit.assert_not_called()


def test_user_cannot_update_another_users_semester(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = None

    with pytest.raises(
        SemesterNotFoundError,
        match="Semester not found",
    ):
        service.update_semester(
            semester_id=1,
            user_id=20,
            semester_data=SemesterUpdate(
                description="Unauthorized update"
            ),
        )

    mock_repository.update.assert_not_called()
    mock_db.commit.assert_not_called()


def test_deleted_semester_cannot_be_updated(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = None

    with pytest.raises(
        SemesterNotFoundError,
        match="Semester not found",
    ):
        service.update_semester(
            semester_id=1,
            user_id=10,
            semester_data=SemesterUpdate(
                description="Updated"
            ),
        )

    mock_repository.update.assert_not_called()
    mock_db.commit.assert_not_called()


def test_empty_update_returns_existing_semester(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    existing_semester: Semester,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )

    result = service.update_semester(
        semester_id=1,
        user_id=10,
        semester_data=SemesterUpdate(),
    )

    assert result is existing_semester
    mock_repository.find_duplicate.assert_not_called()
    mock_repository.update.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.parametrize(
    "field_name",
    [
        "name",
        "academic_year",
        "start_date",
        "end_date",
        "status",
    ],
)
def test_update_rejects_null_for_required_fields(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    existing_semester: Semester,
    field_name: str,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )

    with pytest.raises(
        SemesterValidationError,
        match="Semester fields cannot be null",
    ):
        service.update_semester(
            semester_id=1,
            user_id=10,
            semester_data=SemesterUpdate(
                **{field_name: None}
            ),
        )

    mock_repository.find_duplicate.assert_not_called()
    mock_repository.update.assert_not_called()
    mock_db.commit.assert_not_called()


def test_update_semester_rolls_back_on_database_error(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    existing_semester: Semester,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )
    mock_repository.update.side_effect = SQLAlchemyError(
        "Database error"
    )

    with pytest.raises(SQLAlchemyError):
        service.update_semester(
            semester_id=1,
            user_id=10,
            semester_data=SemesterUpdate(
                description="Updated"
            ),
        )

    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Delete semester
# ---------------------------------------------------------------------------


def test_delete_semester_success(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    existing_semester: Semester,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )
    mock_repository.soft_delete.return_value = (
        existing_semester
    )

    result = service.delete_semester(
        semester_id=1,
        user_id=10,
    )

    assert result is existing_semester
    mock_repository.soft_delete.assert_called_once_with(
        existing_semester
    )
    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()


def test_user_cannot_delete_another_users_semester(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = None

    with pytest.raises(
        SemesterNotFoundError,
        match="Semester not found",
    ):
        service.delete_semester(
            semester_id=1,
            user_id=20,
        )

    mock_repository.soft_delete.assert_not_called()
    mock_db.commit.assert_not_called()


def test_deleted_semester_cannot_be_deleted_again(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = None

    with pytest.raises(
        SemesterNotFoundError,
        match="Semester not found",
    ):
        service.delete_semester(
            semester_id=1,
            user_id=10,
        )

    mock_repository.soft_delete.assert_not_called()
    mock_db.commit.assert_not_called()


def test_delete_semester_rolls_back_on_database_error(
    service: SemesterService,
    mock_db: MagicMock,
    mock_repository: MagicMock,
    existing_semester: Semester,
) -> None:
    mock_repository.get_by_id_and_owner.return_value = (
        existing_semester
    )
    mock_repository.soft_delete.side_effect = SQLAlchemyError(
        "Database error"
    )

    with pytest.raises(SQLAlchemyError):
        service.delete_semester(
            semester_id=1,
            user_id=10,
        )

    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_called_once()
