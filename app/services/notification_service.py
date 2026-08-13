"""Preference-respecting, deduplicated notification sending — see
PHASE_13_NOTIFICATIONS.md.

Two independent guards, both required by this phase's acceptance
criteria, checked in this order:
1. is_enabled -- an opted-out user receives nothing, full stop.
2. dedup (NotificationLog) -- the same event is never sent twice, even
   across separate scheduled-job runs, even if the caller doesn't itself
   track what it already sent.
"""

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.notification import NotificationLog, NotificationPreference, NotificationType
from app.services.notifications import NotificationProvider, get_notification_provider


class NotificationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        provider: NotificationProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self._provider = provider

    def _get_provider(self) -> NotificationProvider:
        if self._provider is not None:
            return self._provider
        return get_notification_provider(self.settings)

    def is_enabled(self, *, user_id: int, notification_type: NotificationType) -> bool:
        preference = (
            self.db.query(NotificationPreference)
            .filter(
                NotificationPreference.user_id == user_id,
                NotificationPreference.notification_type == notification_type,
            )
            .first()
        )
        # Opt-out model: no preference row on file means enabled --
        # see app/models/notification.py's module docstring for why.
        return preference is None or preference.enabled

    def set_preference(
        self, *, user_id: int, notification_type: NotificationType, enabled: bool
    ) -> NotificationPreference:
        preference = (
            self.db.query(NotificationPreference)
            .filter(
                NotificationPreference.user_id == user_id,
                NotificationPreference.notification_type == notification_type,
            )
            .first()
        )
        if preference is None:
            preference = NotificationPreference(
                user_id=user_id, notification_type=notification_type, enabled=enabled
            )
            self.db.add(preference)
        else:
            preference.enabled = enabled
        self.db.commit()
        self.db.refresh(preference)
        return preference

    def list_preferences(self, *, user_id: int) -> dict[NotificationType, bool]:
        rows = (
            self.db.query(NotificationPreference)
            .filter(NotificationPreference.user_id == user_id)
            .all()
        )
        overrides = {row.notification_type: row.enabled for row in rows}
        return {
            notification_type: overrides.get(notification_type, True)
            for notification_type in NotificationType
        }

    def send_reminder(
        self,
        *,
        user_id: int,
        to_email: str,
        notification_type: NotificationType,
        reference_id: str,
        subject: str,
        body: str,
    ) -> NotificationLog | None:
        """Returns the NotificationLog row for this send (newly created,
        or the pre-existing one if this exact event was already sent),
        or None if the user has opted out of this notification type --
        the caller doesn't need to distinguish "opted out" from "already
        sent," both correctly mean "no email went out this call."""

        if not self.is_enabled(user_id=user_id, notification_type=notification_type):
            return None

        existing = (
            self.db.query(NotificationLog)
            .filter(
                NotificationLog.user_id == user_id,
                NotificationLog.notification_type == notification_type,
                NotificationLog.reference_id == reference_id,
            )
            .first()
        )
        if existing is not None:
            return existing

        provider = self._get_provider()
        message_id = provider.send_email(to=to_email, subject=subject, body=body)

        log = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            reference_id=reference_id,
            subject=subject,
            provider_message_id=message_id,
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log
