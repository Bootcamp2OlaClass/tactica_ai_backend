from app.core.config import Settings
from app.services.calendar.base import CalendarProvider
from app.services.calendar.exceptions import CalendarNotConfiguredError


def get_calendar_provider(settings: Settings) -> CalendarProvider:
    """Lazy on purpose -- called only when a sync is actually attempted,
    not at app startup (same pattern as get_llm_provider/
    get_embedding_provider)."""

    if not settings.google_calendar_client_id or not settings.google_calendar_client_secret:
        raise CalendarNotConfiguredError(
            "Google Calendar is not configured (set GOOGLE_CALENDAR_CLIENT_ID and "
            "GOOGLE_CALENDAR_CLIENT_SECRET)."
        )

    from app.services.calendar.google_provider import GoogleCalendarProvider

    return GoogleCalendarProvider()
