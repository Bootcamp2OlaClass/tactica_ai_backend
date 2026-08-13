import secrets
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.exceptions.calendar import CalendarNotConnectedError
from app.exceptions.task import TaskNotFoundError
from app.models.user import User
from app.schemas.calendar import (
    CalendarAuthorizationResponse,
    CalendarConnectionStatusResponse,
    CalendarConnectRequest,
    CalendarSyncResponse,
)
from app.schemas.common import ErrorResponse
from app.services.calendar.exceptions import (
    CalendarNotConfiguredError,
    CalendarProviderError,
    CalendarTransientError,
)
from app.services.calendar_connection import CalendarConnectionService
from app.services.calendar_sync import CalendarSyncService
from app.services.task import TaskService

router = APIRouter(
    prefix="/api/v1",
    tags=["Calendar"],
)

CALENDAR_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Authentication required or invalid",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Task not found, or no calendar connection exists",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "Google Calendar is not configured or temporarily unavailable",
    },
}


def get_calendar_connection_service(
    db: Session = Depends(get_db),
) -> CalendarConnectionService:
    return CalendarConnectionService(db, get_settings())


def get_calendar_sync_service(db: Session = Depends(get_db)) -> CalendarSyncService:
    return CalendarSyncService(db, get_settings())


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    return TaskService(db)


def raise_calendar_http_exception(error: Exception) -> NoReturn:
    if isinstance(error, (CalendarNotConnectedError, TaskNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if isinstance(error, (CalendarNotConfiguredError, CalendarTransientError, CalendarProviderError)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error


@router.get(
    "/calendar/authorize",
    response_model=CalendarAuthorizationResponse,
    status_code=status.HTTP_200_OK,
    responses=CALENDAR_ERROR_RESPONSES,
)
def get_calendar_authorization_url(
    current_user: User = Depends(get_current_user),
    service: CalendarConnectionService = Depends(get_calendar_connection_service),
) -> CalendarAuthorizationResponse:
    """`state` is a random opaque token, NOT yet verified round-trip
    against a stored session value -- CSRF protection for this OAuth flow
    is an explicit, tracked gap (see PHASE_12_CALENDAR.md's Remaining
    Limitations and Phase 14's security-review scope), not silently
    assumed complete."""
    try:
        url = service.get_authorization_url(state=secrets.token_urlsafe(24))
    except CalendarNotConfiguredError as error:
        raise_calendar_http_exception(error)
    return CalendarAuthorizationResponse(authorization_url=url)


@router.post(
    "/calendar/connect",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=CALENDAR_ERROR_RESPONSES,
)
def connect_calendar(
    body: CalendarConnectRequest,
    current_user: User = Depends(get_current_user),
    service: CalendarConnectionService = Depends(get_calendar_connection_service),
) -> None:
    try:
        service.connect(user_id=current_user.id, code=body.code)
    except (CalendarNotConfiguredError, CalendarTransientError) as error:
        raise_calendar_http_exception(error)


@router.delete(
    "/calendar/disconnect",
    status_code=status.HTTP_204_NO_CONTENT,
)
def disconnect_calendar(
    current_user: User = Depends(get_current_user),
    service: CalendarConnectionService = Depends(get_calendar_connection_service),
) -> None:
    service.disconnect(user_id=current_user.id)


@router.get(
    "/calendar/status",
    response_model=CalendarConnectionStatusResponse,
    status_code=status.HTTP_200_OK,
)
def get_calendar_status(
    current_user: User = Depends(get_current_user),
    service: CalendarConnectionService = Depends(get_calendar_connection_service),
) -> CalendarConnectionStatusResponse:
    return CalendarConnectionStatusResponse(connected=service.is_connected(user_id=current_user.id))


@router.post(
    "/tasks/{task_id}/calendar-sync",
    response_model=CalendarSyncResponse,
    status_code=status.HTTP_200_OK,
    responses=CALENDAR_ERROR_RESPONSES,
)
def sync_task_to_calendar(
    task_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    sync_service: CalendarSyncService = Depends(get_calendar_sync_service),
    task_service: TaskService = Depends(get_task_service),
) -> CalendarSyncResponse:
    try:
        task = task_service.get_task(task_id=task_id, user_id=current_user.id)
        sync = sync_service.sync_task(task=task, user_id=current_user.id)
    except (
        TaskNotFoundError,
        CalendarNotConnectedError,
        CalendarNotConfiguredError,
        CalendarTransientError,
        CalendarProviderError,
    ) as error:
        raise_calendar_http_exception(error)
    return CalendarSyncResponse.model_validate(sync)


@router.delete(
    "/tasks/{task_id}/calendar-sync",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=CALENDAR_ERROR_RESPONSES,
)
def unsync_task_from_calendar(
    task_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    sync_service: CalendarSyncService = Depends(get_calendar_sync_service),
    task_service: TaskService = Depends(get_task_service),
) -> None:
    try:
        task = task_service.get_task(task_id=task_id, user_id=current_user.id)
        sync_service.unsync_task(task=task, user_id=current_user.id)
    except (TaskNotFoundError, CalendarNotConnectedError) as error:
        raise_calendar_http_exception(error)
