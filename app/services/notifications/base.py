"""Provider-agnostic email notification abstraction — see
PHASE_13_NOTIFICATIONS.md.

Mirrors app/services/calendar/base.py's (Phase 12) and
app/services/storage/base.py's (Phase 03, ADR-004) shape deliberately:
Resend today, an FCM push provider could slot in behind the same
interface shape later without touching NotificationService (the FCM
implementation itself is FUTURE per BACKLOG.md — this phase prepares the
seam, per its own original scope note, without building push).
"""

from abc import ABC, abstractmethod


class NotificationProvider(ABC):
    @abstractmethod
    def send_email(self, *, to: str, subject: str, body: str) -> str:
        """Returns the provider's own message id -- stored on
        NotificationLog.provider_message_id for auditability, not used
        for dedup (dedup is keyed on reference_id, decided before this is
        ever called -- see NotificationService.send_reminder)."""
