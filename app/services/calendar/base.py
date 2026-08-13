"""Provider-agnostic calendar abstraction — see PHASE_12_CALENDAR.md.

Mirrors app/services/storage/base.py's (Phase 03, ADR-004) and
app/services/llm/base.py's (Phase 06, ADR-002) shape deliberately: one
real provider today (Google), swappable behind this interface without
touching `CalendarSyncService`, same pattern proven twice already.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CalendarEventInput:
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime


class CalendarProvider(ABC):
    @abstractmethod
    def create_event(self, *, access_token: str, event: CalendarEventInput) -> str:
        """Returns the provider's own event id -- the value
        CalendarSync.provider_event_id stores, and the sole mechanism
        idempotent re-sync relies on (see app/services/calendar_sync.py)."""

    @abstractmethod
    def update_event(
        self, *, access_token: str, provider_event_id: str, event: CalendarEventInput
    ) -> None:
        """Updates an existing event in place -- called instead of
        create_event whenever a provider_event_id is already known, which
        is the entire duplicate-prevention mechanism."""

    @abstractmethod
    def delete_event(self, *, access_token: str, provider_event_id: str) -> None:
        """Must not raise if the event is already gone provider-side
        (e.g. deleted manually by the student in Google Calendar) --
        unsync is a "make sure it's gone" operation, not a strict
        precondition check."""
