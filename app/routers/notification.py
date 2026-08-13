from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.notification import NotificationType
from app.models.user import User
from app.schemas.notification import (
    NotificationPreferencesResponse,
    NotificationPreferenceUpdateRequest,
)
from app.services.notification_service import NotificationService

router = APIRouter(
    prefix="/api/v1",
    tags=["Notifications"],
)


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(db, get_settings())


@router.get(
    "/notification-preferences",
    response_model=NotificationPreferencesResponse,
    status_code=status.HTTP_200_OK,
)
def get_notification_preferences(
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPreferencesResponse:
    return NotificationPreferencesResponse(
        preferences=service.list_preferences(user_id=current_user.id)
    )


@router.put(
    "/notification-preferences/{notification_type}",
    response_model=NotificationPreferencesResponse,
    status_code=status.HTTP_200_OK,
)
def update_notification_preference(
    body: NotificationPreferenceUpdateRequest,
    notification_type: NotificationType = Path(...),
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPreferencesResponse:
    service.set_preference(
        user_id=current_user.id,
        notification_type=notification_type,
        enabled=body.enabled,
    )
    return NotificationPreferencesResponse(
        preferences=service.list_preferences(user_id=current_user.id)
    )
