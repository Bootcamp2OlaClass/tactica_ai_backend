from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.calendar import CalendarSyncStatus


class CalendarAuthorizationResponse(BaseModel):
    authorization_url: str


class CalendarConnectRequest(BaseModel):
    code: str


class CalendarConnectionStatusResponse(BaseModel):
    connected: bool


class CalendarSyncResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: int
    provider_event_id: str | None
    sync_status: CalendarSyncStatus
    sync_error: str | None
    last_synced_at: datetime | None
