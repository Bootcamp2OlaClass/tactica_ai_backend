class CalendarError(Exception):
    """Base exception for calendar sync operations."""


class CalendarNotConnectedError(CalendarError):
    """Raised when sync/unsync is attempted but the student hasn't
    connected a Google Calendar account yet."""
