from typing import Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.exceptions.course import (
    CourseConflictError,
    CourseError,
    CourseNotFoundError,
    CourseValidationError,
)
from app.models.course import CourseStatus
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.course import (
    CourseCreate,
    CourseCreateRequest,
    CourseListResponse,
    CourseResponse,
    CourseUpdate,
)
from app.services.course import CourseService


router = APIRouter(
    prefix="/api/v1",
    tags=["Courses"],
)

COURSE_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {
        "model": ErrorResponse,
        "description": "Invalid course operation",
    },
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Authentication required or invalid",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Course or semester not found",
    },
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "Course code conflicts with an existing course",
    },
}

CourseSortField = Literal[
    "course_code",
    "name",
    "status",
    "created_at",
    "updated_at",
]
SortOrder = Literal["asc", "desc"]


def get_course_service(
    db: Session = Depends(get_db),
) -> CourseService:
    return CourseService(db)


def raise_course_http_exception(error: CourseError) -> NoReturn:
    if isinstance(error, CourseConflictError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, CourseNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, CourseValidationError):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    raise HTTPException(
        status_code=status_code,
        detail=str(error),
    ) from error


@router.post(
    "/semesters/{semester_id}/courses",
    response_model=CourseResponse,
    status_code=status.HTTP_201_CREATED,
    responses=COURSE_ERROR_RESPONSES,
)
def create_course(
    course_data: CourseCreateRequest,
    semester_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    service: CourseService = Depends(get_course_service),
) -> CourseResponse:
    try:
        return service.create_course(
            user_id=current_user.id,
            course_data=CourseCreate(
                semester_id=semester_id,
                **course_data.model_dump(),
            ),
        )
    except CourseError as error:
        raise_course_http_exception(error)


@router.get(
    "/semesters/{semester_id}/courses",
    response_model=CourseListResponse,
    responses=COURSE_ERROR_RESPONSES,
)
def list_semester_courses(
    semester_id: int = Path(ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: CourseService = Depends(get_course_service),
) -> CourseListResponse:
    try:
        return service.list_courses(
            user_id=current_user.id,
            semester_id=semester_id,
            page=page,
            page_size=page_size,
        )
    except CourseError as error:
        raise_course_http_exception(error)


@router.get(
    "/courses",
    response_model=CourseListResponse,
    responses=COURSE_ERROR_RESPONSES,
)
def list_courses(
    semester_id: int | None = Query(default=None, ge=1),
    course_status: CourseStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: CourseSortField = Query(default="created_at"),
    sort_order: SortOrder = Query(default="desc"),
    current_user: User = Depends(get_current_user),
    service: CourseService = Depends(get_course_service),
) -> CourseListResponse:
    try:
        return service.list_courses(
            user_id=current_user.id,
            semester_id=semester_id,
            status=course_status,
            search=search,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except CourseError as error:
        raise_course_http_exception(error)


@router.get(
    "/courses/{course_id}",
    response_model=CourseResponse,
    responses=COURSE_ERROR_RESPONSES,
)
def get_course(
    course_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    service: CourseService = Depends(get_course_service),
) -> CourseResponse:
    try:
        return service.get_course(
            course_id=course_id,
            user_id=current_user.id,
        )
    except CourseError as error:
        raise_course_http_exception(error)


@router.patch(
    "/courses/{course_id}",
    response_model=CourseResponse,
    responses=COURSE_ERROR_RESPONSES,
)
def update_course(
    course_data: CourseUpdate,
    course_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    service: CourseService = Depends(get_course_service),
) -> CourseResponse:
    try:
        return service.update_course(
            course_id=course_id,
            user_id=current_user.id,
            course_data=course_data,
        )
    except CourseError as error:
        raise_course_http_exception(error)


@router.delete(
    "/courses/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=COURSE_ERROR_RESPONSES,
)
def delete_course(
    course_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    service: CourseService = Depends(get_course_service),
) -> Response:
    try:
        service.delete_course(
            course_id=course_id,
            user_id=current_user.id,
        )
    except CourseError as error:
        raise_course_http_exception(error)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
