from app.core.config import Settings
from app.services.notifications.base import NotificationProvider
from app.services.notifications.exceptions import NotificationNotConfiguredError


def get_notification_provider(settings: Settings) -> NotificationProvider:
    """Lazy on purpose -- called only when a send is actually attempted,
    not at app startup (same pattern as every other provider factory)."""

    if not settings.resend_api_key or not settings.resend_from_address:
        raise NotificationNotConfiguredError(
            "Email notifications are not configured (set RESEND_API_KEY and "
            "RESEND_FROM_ADDRESS)."
        )

    from app.services.notifications.resend_provider import ResendProvider

    return ResendProvider(
        api_key=settings.resend_api_key, from_address=settings.resend_from_address
    )
