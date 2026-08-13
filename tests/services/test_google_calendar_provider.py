"""GoogleCalendarProvider tests -- see PHASE_12_CALENDAR.md.

Exercises the real REST client code path against httpx.MockTransport, the
same honesty standard (and the same NOT VERIFIED-against-the-real-API
caveat) as every LLM/embedding provider in this codebase.
"""

from datetime import datetime, timezone

import httpx
import pytest

from app.services.calendar.base import CalendarEventInput
from app.services.calendar.exceptions import CalendarProviderError, CalendarTransientError
from app.services.calendar.google_provider import CALENDAR_API_BASE, GoogleCalendarProvider

EVENT = CalendarEventInput(
    title="Essay due",
    description=None,
    start_at=datetime(2026, 8, 20, 9, tzinfo=timezone.utc),
    end_at=datetime(2026, 8, 20, 9, 30, tzinfo=timezone.utc),
)


def _provider_with(handler) -> GoogleCalendarProvider:
    client = httpx.Client(base_url=CALENDAR_API_BASE, transport=httpx.MockTransport(handler))
    return GoogleCalendarProvider(client=client)


def test_create_event_returns_the_providers_event_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token-1"
        return httpx.Response(200, json={"id": "google-event-1"})

    provider = _provider_with(handler)

    event_id = provider.create_event(access_token="token-1", event=EVENT)

    assert event_id == "google-event-1"


def test_create_event_raises_transient_error_on_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    provider = _provider_with(handler)

    with pytest.raises(CalendarTransientError):
        provider.create_event(access_token="token-1", event=EVENT)


def test_create_event_raises_provider_error_on_rejection():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="invalid event")

    provider = _provider_with(handler)

    with pytest.raises(CalendarProviderError):
        provider.create_event(access_token="token-1", event=EVENT)


def test_update_event_puts_to_the_event_specific_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path.endswith("/existing-event-id")
        return httpx.Response(200, json={"id": "existing-event-id"})

    provider = _provider_with(handler)

    provider.update_event(access_token="token-1", provider_event_id="existing-event-id", event=EVENT)


def test_delete_event_treats_already_gone_as_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    provider = _provider_with(handler)

    provider.delete_event(access_token="token-1", provider_event_id="already-gone")  # must not raise


def test_delete_event_raises_transient_error_on_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    provider = _provider_with(handler)

    with pytest.raises(CalendarTransientError):
        provider.delete_event(access_token="token-1", provider_event_id="event-1")
