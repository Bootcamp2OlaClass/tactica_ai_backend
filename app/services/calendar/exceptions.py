class CalendarNotConfiguredError(Exception):
    """Raised when calendar sync is attempted but no Google OAuth client
    is configured (GOOGLE_CALENDAR_CLIENT_ID/SECRET). Never raised at app
    boot -- only when sync is actually attempted, matching the optional-
    infrastructure pattern used for LLM/embedding providers."""


class CalendarProviderError(Exception):
    """A permanent provider-side failure (e.g. the event was rejected as
    invalid) -- retrying the same request is unlikely to succeed."""


class CalendarTransientError(Exception):
    """A transient provider-side failure (rate limit, timeout, temporary
    API outage) -- retryable."""
