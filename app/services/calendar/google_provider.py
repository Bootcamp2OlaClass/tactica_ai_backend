"""Google Calendar implementation of CalendarProvider — see
PHASE_12_CALENDAR.md.

NOT VERIFIED against the real Google Calendar API: no OAuth credentials
were available in this environment. Exercised only via a fake-provider
test seam, same honesty standard as R2StorageProvider (ADR-004) and
every LLM/embedding provider (ADR-002/007). Uses `httpx` directly against
the Calendar API v3 REST surface rather than adding the
`google-api-python-client` dependency -- a plain REST client is enough
for the three operations this phase needs and keeps the dependency
footprint the same as every other provider in this codebase.
"""

import httpx

from app.services.calendar.base import CalendarEventInput, CalendarProvider
from app.services.calendar.exceptions import CalendarProviderError, CalendarTransientError

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _event_body(event: CalendarEventInput) -> dict:
    return {
        "summary": event.title,
        "description": event.description,
        "start": {"dateTime": event.start_at.isoformat()},
        "end": {"dateTime": event.end_at.isoformat()},
    }


class GoogleCalendarProvider(CalendarProvider):
    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(base_url=CALENDAR_API_BASE, timeout=10.0)

    def _headers(self, access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}

    def create_event(self, *, access_token: str, event: CalendarEventInput) -> str:
        try:
            response = self._client.post(
                "", json=_event_body(event), headers=self._headers(access_token)
            )
        except httpx.HTTPError as exc:
            raise CalendarTransientError(f"Google Calendar request failed: {exc}") from exc

        if response.status_code >= 500 or response.status_code == 429:
            raise CalendarTransientError(
                f"Google Calendar returned a transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise CalendarProviderError(
                f"Google Calendar rejected the event: {response.status_code} {response.text}"
            )

        event_id = response.json().get("id")
        if not event_id:
            raise CalendarProviderError("Google Calendar did not return an event id.")
        return event_id

    def update_event(
        self, *, access_token: str, provider_event_id: str, event: CalendarEventInput
    ) -> None:
        try:
            response = self._client.put(
                f"/{provider_event_id}",
                json=_event_body(event),
                headers=self._headers(access_token),
            )
        except httpx.HTTPError as exc:
            raise CalendarTransientError(f"Google Calendar request failed: {exc}") from exc

        if response.status_code >= 500 or response.status_code == 429:
            raise CalendarTransientError(
                f"Google Calendar returned a transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise CalendarProviderError(
                f"Google Calendar rejected the update: {response.status_code} {response.text}"
            )

    def delete_event(self, *, access_token: str, provider_event_id: str) -> None:
        try:
            response = self._client.delete(
                f"/{provider_event_id}", headers=self._headers(access_token)
            )
        except httpx.HTTPError as exc:
            raise CalendarTransientError(f"Google Calendar request failed: {exc}") from exc

        # 404/410 -- already gone provider-side -- is a successful outcome
        # for a "make sure it's deleted" operation, not an error.
        if response.status_code in (404, 410) or response.status_code < 300:
            return
        if response.status_code >= 500 or response.status_code == 429:
            raise CalendarTransientError(
                f"Google Calendar returned a transient error: {response.status_code}"
            )
        raise CalendarProviderError(
            f"Google Calendar rejected the delete: {response.status_code} {response.text}"
        )
