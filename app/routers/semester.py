from typing import Literal, NoReturn

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.exceptions.semester import (
    SemesterConflictError,
    SemesterNotFoundError,
    SemesterValidationError,
)
from app.models.semester import SemesterStatus
from app.models.user import User
from app.schemas.semester import (
    SemesterCreate,
    SemesterListResponse,
    SemesterResponse,
    SemesterUpdate,
)
from app.services.semester import SemesterService


SemesterSortField = Literal[
    "id",
    "name",
    "academic_year",
    "start_date",
    "end_date",
    "status",
    "created_at",
    "updated_at",
]

SemesterSortOrder = Literal["asc", "desc"]


router = APIRouter(
    prefix="/api/v1/semesters",
    tags=["Semesters"],
)


def raise_http_error(error: Exception) -> NoReturn:
    """Translate semester domain errors into HTTP responses."""

    if isinstance(error, SemesterNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    if isinstance(error, SemesterConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    if isinstance(error, SemesterValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    raise error


@router.post(
    "",
    response_model=SemesterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Duplicate active semester",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Invalid semester data",
        },
    },
)
def create_semester(
    semester_data: SemesterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SemesterResponse:
    service = SemesterService(db)

    try:
        return service.create_semester(
            user_id=current_user.id,
            semester_data=semester_data,
        )
    except (
        SemesterConflictError,
        SemesterValidationError,
    ) as error:
        raise_http_error(error)


@router.get(
    "",
    response_model=SemesterListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Invalid query parameters",
        },
    },
)
def list_semesters(
    page: int = Query(
        default=1,
        ge=1,
        description="Page number, starting from 1",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of semesters per page",
    ),
    search: str | None = Query(
        default=None,
        description="Search by semester name",
    ),
    semester_status: SemesterStatus | None = Query(
        default=None,
        alias="status",
        description="Filter by semester status",
    ),
    sort_by: SemesterSortField = Query(
        default="created_at",
        description="Field used to sort the results",
    ),
    sort_order: SemesterSortOrder = Query(
        default="desc",
        description="Sort direction",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SemesterListResponse:
    service = SemesterService(db)

    try:
        result = service.list_semesters(
            user_id=current_user.id,
            page=page,
            page_size=page_size,
            search=search,
            status=semester_status,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except SemesterValidationError as error:
        raise_http_error(error)

    return SemesterListResponse(**result)


@router.get(
    "/{semester_id}",
    response_model=SemesterResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Semester not found or inaccessible",
        },
    },
)
def get_semester(
    semester_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SemesterResponse:
    service = SemesterService(db)

    try:
        return service.get_semester(
            semester_id=semester_id,
            user_id=current_user.id,
        )
    except SemesterNotFoundError as error:
        raise_http_error(error)


@router.patch(
    "/{semester_id}",
    response_model=SemesterResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Semester not found or inaccessible",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Update conflicts with an existing semester",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Invalid semester update",
        },
    },
)
def update_semester(
    semester_id: int,
    semester_data: SemesterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SemesterResponse:
    service = SemesterService(db)

    try:
        return service.update_semester(
            semester_id=semester_id,
            user_id=current_user.id,
            semester_data=semester_data,
        )
    except (
        SemesterNotFoundError,
        SemesterConflictError,
        SemesterValidationError,
    ) as error:
        raise_http_error(error)


@router.delete(
    "/{semester_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Semester not found or inaccessible",
        },
        status.HTTP_204_NO_CONTENT: {
            "description": "Semester deleted successfully",
        },
    },
)
def delete_semester(
    semester_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    service = SemesterService(db)

    try:
        service.delete_semester(
            semester_id=semester_id,
            user_id=current_user.id,
        )
    except SemesterNotFoundError as error:
        raise_http_error(error)

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )