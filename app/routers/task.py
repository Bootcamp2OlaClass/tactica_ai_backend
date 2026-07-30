from datetime import datetime
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
from app.exceptions.task import (
    TaskConflictError,
    TaskNotFoundError,
    TaskValidationError,
)
from app.models.task import (
    TaskPriority,
    TaskStatus,
    TaskType,
)
from app.models.user import User
from app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
)
from app.services.task import TaskService


TaskSortField = Literal[
    "title",
    "status",
    "priority",
    "task_type",
    "due_at",
    "created_at",
    "updated_at",
]

TaskSortOrder = Literal["asc", "desc"]


router = APIRouter(
    tags=["Tasks"],
)


def raise_http_error(error: Exception) -> NoReturn:
    """Translate task domain exceptions into HTTP responses."""

    if isinstance(error, TaskNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    if isinstance(error, TaskConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    if isinstance(error, TaskValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    raise error


@router.post(
    "/api/v1/courses/{course_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Course not found or inaccessible",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Invalid task data",
        },
    },
)
def create_task(
    course_id: int,
    task_data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    service = TaskService(db)

    try:
        return service.create_task(
            user_id=current_user.id,
            course_id=course_id,
            task_data=task_data,
        )
    except (
        TaskNotFoundError,
        TaskValidationError,
    ) as error:
        raise_http_error(error)


@router.get(
    "/api/v1/tasks",
    response_model=TaskListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Filtered course not found or inaccessible",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Invalid task filter parameters",
        },
    },
)
def list_tasks(
    page: int = Query(
        default=1,
        ge=1,
        description="Page number starting from 1",
        examples=[1],
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of tasks returned per page",
        examples=[20],
    ),
    course_id: int | None = Query(
        default=None,
        gt=0,
        description="Filter tasks by course ID",
        examples=[12],
    ),
    semester_id: int | None = Query(
        default=None,
        gt=0,
        description="Filter tasks by semester ID",
        examples=[3],
    ),
    task_status: TaskStatus | None = Query(
        default=None,
        alias="status",
        description="Filter tasks by status",
        examples=["todo"],
    ),
    priority: TaskPriority | None = Query(
        default=None,
        description="Filter tasks by priority",
        examples=["high"],
    ),
    task_type: TaskType | None = Query(
        default=None,
        description="Filter tasks by type",
        examples=["assignment"],
    ),
    due_from: datetime | None = Query(
        default=None,
        description=(
            "Return tasks due on or after this timezone-aware timestamp"
        ),
        examples=["2026-08-01T00:00:00Z"],
    ),
    due_to: datetime | None = Query(
        default=None,
        description=(
            "Return tasks due on or before this timezone-aware timestamp"
        ),
        examples=["2026-08-31T23:59:59Z"],
    ),
    overdue: bool | None = Query(
        default=None,
        description="Filter tasks by overdue state",
        examples=[True],
    ),
    search: str | None = Query(
        default=None,
        description="Search task titles and descriptions",
        examples=["database assignment"],
    ),
    sort_by: TaskSortField = Query(
        default="created_at",
        description="Field used to sort task results",
        examples=["due_at"],
    ),
    sort_order: TaskSortOrder = Query(
        default="desc",
        description="Sort direction",
        examples=["asc"],
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskListResponse:
    service = TaskService(db)

    try:
        result = service.list_tasks(
            user_id=current_user.id,
            page=page,
            page_size=page_size,
            course_id=course_id,
            semester_id=semester_id,
            status=task_status,
            priority=priority,
            task_type=task_type,
            due_from=due_from,
            due_to=due_to,
            overdue=overdue,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except (
        TaskNotFoundError,
        TaskValidationError,
    ) as error:
        raise_http_error(error)

    return TaskListResponse(**result)


@router.get(
    "/api/v1/tasks/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Task not found or inaccessible",
        },
    },
)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    service = TaskService(db)

    try:
        return service.get_task(
            task_id=task_id,
            user_id=current_user.id,
        )
    except TaskNotFoundError as error:
        raise_http_error(error)


@router.patch(
    "/api/v1/tasks/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Task not found or inaccessible",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Invalid task update or state",
        },
    },
)
def update_task(
    task_id: int,
    task_data: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    service = TaskService(db)

    try:
        return service.update_task(
            task_id=task_id,
            user_id=current_user.id,
            task_data=task_data,
        )
    except (
        TaskNotFoundError,
        TaskValidationError,
    ) as error:
        raise_http_error(error)


@router.post(
    "/api/v1/tasks/{task_id}/complete",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Task not found or inaccessible",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Task cannot be completed from its current state",
        },
    },
)
def complete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    service = TaskService(db)

    try:
        return service.mark_task_completed(
            task_id=task_id,
            user_id=current_user.id,
        )
    except (
        TaskNotFoundError,
        TaskConflictError,
    ) as error:
        raise_http_error(error)


@router.post(
    "/api/v1/tasks/{task_id}/reopen",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Task not found or inaccessible",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Task cannot be reopened from its current state",
        },
    },
)
def reopen_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    service = TaskService(db)

    try:
        return service.reopen_task(
            task_id=task_id,
            user_id=current_user.id,
        )
    except (
        TaskNotFoundError,
        TaskConflictError,
    ) as error:
        raise_http_error(error)


@router.delete(
    "/api/v1/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid authentication token",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Task not found or inaccessible",
        },
        status.HTTP_204_NO_CONTENT: {
            "description": "Task deleted successfully",
        },
    },
)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    service = TaskService(db)

    try:
        service.delete_task(
            task_id=task_id,
            user_id=current_user.id,
        )
    except TaskNotFoundError as error:
        raise_http_error(error)

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )