"""Idempotent Google Calendar sync — see PHASE_12_CALENDAR.md.

The whole "no duplicate events" acceptance criterion lives in one place:
`sync_task` only ever calls `create_event` when no `CalendarSync` row with
a `provider_event_id` exists yet for that task; every subsequent call for
the same task calls `update_event` against the already-known id instead.
There is no other code path that creates an event.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.calendar import CalendarNotConnectedError
from app.models.calendar import CalendarConnection, CalendarSync, CalendarSyncStatus
from app.models.task import Task
from app.services.calendar import CalendarEventInput, CalendarProvider, get_calendar_provider
from app.services.calendar.exceptions import CalendarProviderError, CalendarTransientError
from app.services.calendar_oauth import CalendarOAuthService

logger = logging.getLogger(__name__)

DEFAULT_EVENT_DURATION_MINUTES = 30
# Refresh proactively rather than reactively -- avoids a sync failing
# mid-call on an access token that expires a few seconds into the request.
TOKEN_REFRESH_MARGIN = timedelta(minutes=5)


class CalendarSyncService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        calendar_provider: CalendarProvider | None = None,
        oauth_service: CalendarOAuthService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self._calendar_provider = calendar_provider
        self._oauth_service = oauth_service or CalendarOAuthService(settings)

    def _get_provider(self) -> CalendarProvider:
        if self._calendar_provider is not None:
            return self._calendar_provider
        return get_calendar_provider(self.settings)

    def _get_connection(self, user_id: int) -> CalendarConnection:
        connection = (
            self.db.query(CalendarConnection)
            .filter(CalendarConnection.user_id == user_id)
            .first()
        )
        if connection is None:
            raise CalendarNotConnectedError("No Google Calendar connection for this user.")
        return self._ensure_fresh_token(connection)

    def _ensure_fresh_token(self, connection: CalendarConnection) -> CalendarConnection:
        if connection.token_expires_at - TOKEN_REFRESH_MARGIN > datetime.now(timezone.utc):
            return connection

        tokens = self._oauth_service.refresh_access_token(refresh_token=connection.refresh_token)
        connection.access_token = tokens.access_token
        connection.refresh_token = tokens.refresh_token
        connection.token_expires_at = tokens.expires_at
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def _get_or_create_sync_row(self, task_id: int) -> CalendarSync:
        sync = self.db.query(CalendarSync).filter(CalendarSync.task_id == task_id).first()
        if sync is None:
            sync = CalendarSync(task_id=task_id, sync_status=CalendarSyncStatus.FAILED)
            self.db.add(sync)
            self.db.flush()
        return sync

    def sync_task(self, *, task: Task, user_id: int) -> CalendarSync:
        connection = self._get_connection(user_id)
        provider = self._get_provider()
        sync = self._get_or_create_sync_row(task.id)

        due_at = task.due_at or datetime.now(timezone.utc)
        event = CalendarEventInput(
            title=task.title,
            description=task.description,
            start_at=due_at,
            end_at=due_at + timedelta(minutes=DEFAULT_EVENT_DURATION_MINUTES),
        )

        try:
            if sync.provider_event_id is not None:
                # Idempotent path: same task synced again -> update the
                # existing event, never create a second one.
                provider.update_event(
                    access_token=connection.access_token,
                    provider_event_id=sync.provider_event_id,
                    event=event,
                )
            else:
                sync.provider_event_id = provider.create_event(
                    access_token=connection.access_token, event=event
                )
        except (CalendarProviderError, CalendarTransientError) as exc:
            sync.sync_status = CalendarSyncStatus.FAILED
            sync.sync_error = str(exc)
            self.db.commit()
            raise

        sync.sync_status = CalendarSyncStatus.SYNCED
        sync.sync_error = None
        sync.last_synced_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(sync)
        return sync

    def unsync_task(self, *, task: Task, user_id: int) -> None:
        """Removes the synced event, if any. A task that was never synced
        is a no-op, not an error -- this is a "make sure it's gone"
        operation, called unconditionally from task deletion (see
        app/services/task.py's non-fatal hook)."""
        sync = self.db.query(CalendarSync).filter(CalendarSync.task_id == task.id).first()
        if sync is None or sync.provider_event_id is None:
            if sync is not None:
                self.db.delete(sync)
                self.db.commit()
            return

        connection = self._get_connection(user_id)
        provider = self._get_provider()
        provider.delete_event(
            access_token=connection.access_token, provider_event_id=sync.provider_event_id
        )

        self.db.delete(sync)
        self.db.commit()
