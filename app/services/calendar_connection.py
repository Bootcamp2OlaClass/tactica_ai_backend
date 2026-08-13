"""Connect/disconnect a student's Google Calendar — see PHASE_12_CALENDAR.md."""

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.calendar import CalendarConnection
from app.services.calendar_oauth import CalendarOAuthService


class CalendarConnectionService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        oauth_service: CalendarOAuthService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.oauth_service = oauth_service or CalendarOAuthService(settings)

    def get_authorization_url(self, *, state: str) -> str:
        return self.oauth_service.get_authorization_url(state=state)

    def connect(self, *, user_id: int, code: str) -> CalendarConnection:
        tokens = self.oauth_service.exchange_code_for_tokens(code=code)

        connection = (
            self.db.query(CalendarConnection)
            .filter(CalendarConnection.user_id == user_id)
            .first()
        )
        if connection is None:
            connection = CalendarConnection(
                user_id=user_id,
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                token_expires_at=tokens.expires_at,
            )
            self.db.add(connection)
        else:
            connection.access_token = tokens.access_token
            connection.refresh_token = tokens.refresh_token
            connection.token_expires_at = tokens.expires_at

        self.db.commit()
        self.db.refresh(connection)
        return connection

    def disconnect(self, *, user_id: int) -> None:
        connection = (
            self.db.query(CalendarConnection)
            .filter(CalendarConnection.user_id == user_id)
            .first()
        )
        if connection is not None:
            self.db.delete(connection)
            self.db.commit()

    def is_connected(self, *, user_id: int) -> bool:
        return (
            self.db.query(CalendarConnection)
            .filter(CalendarConnection.user_id == user_id)
            .first()
            is not None
        )
