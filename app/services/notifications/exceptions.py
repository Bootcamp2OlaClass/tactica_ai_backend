class NotificationNotConfiguredError(Exception):
    """Raised when a send is attempted but no email provider is
    configured (RESEND_API_KEY/RESEND_FROM_ADDRESS). Never raised at app
    boot -- only when a send is actually attempted."""


class NotificationProviderError(Exception):
    """A permanent provider-side failure (e.g. the recipient address was
    rejected) -- retrying the same request is unlikely to succeed."""


class NotificationTransientError(Exception):
    """A transient provider-side failure (rate limit, timeout, temporary
    API outage) -- retryable."""
