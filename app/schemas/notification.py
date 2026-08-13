from pydantic import BaseModel

from app.models.notification import NotificationType


class NotificationPreferenceUpdateRequest(BaseModel):
    enabled: bool


class NotificationPreferencesResponse(BaseModel):
    preferences: dict[NotificationType, bool]
