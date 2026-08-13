"""CalendarOAuthService tests -- see PHASE_12_CALENDAR.md.

Uses httpx.MockTransport (a real httpx testing feature) to stand in for
Google's token endpoint -- the same "exercise the real client code path
against a fake transport" honesty standard as every other provider in
this codebase, since no real Google OAuth credentials exist in this
environment to test against directly.
"""

from types import SimpleNamespace

import httpx
import pytest

from app.services.calendar.exceptions import CalendarNotConfiguredError, CalendarTransientError
from app.services.calendar_oauth import CalendarOAuthService

SETTINGS = SimpleNamespace(
    google_calendar_client_id="client-id",
    google_calendar_client_secret="client-secret",
    google_calendar_redirect_uri="https://example.com/callback",
)

UNCONFIGURED_SETTINGS = SimpleNamespace(
    google_calendar_client_id=None,
    google_calendar_client_secret=None,
    google_calendar_redirect_uri=None,
)


def _client_with(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_get_authorization_url_includes_the_required_google_params():
    service = CalendarOAuthService(SETTINGS)

    url = service.get_authorization_url(state="abc123")

    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=client-id" in url
    assert "state=abc123" in url
    assert "access_type=offline" in url  # required to receive a refresh_token


def test_get_authorization_url_raises_when_not_configured():
    service = CalendarOAuthService(UNCONFIGURED_SETTINGS)

    with pytest.raises(CalendarNotConfiguredError):
        service.get_authorization_url(state="abc123")


def test_exchange_code_for_tokens_parses_a_successful_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/token"
        return httpx.Response(
            200, json={"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600}
        )

    service = CalendarOAuthService(SETTINGS, http_client=_client_with(handler))

    tokens = service.exchange_code_for_tokens(code="auth-code")

    assert tokens.access_token == "at-1"
    assert tokens.refresh_token == "rt-1"


def test_exchange_code_for_tokens_raises_on_a_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    service = CalendarOAuthService(SETTINGS, http_client=_client_with(handler))

    with pytest.raises(CalendarTransientError):
        service.exchange_code_for_tokens(code="auth-code")


def test_refresh_access_token_falls_back_to_the_existing_refresh_token():
    """Google only returns a new refresh_token on first consent -- a
    refresh response with none must fall back to the one already on
    file, not lose it."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "at-2", "expires_in": 3600})

    service = CalendarOAuthService(SETTINGS, http_client=_client_with(handler))

    tokens = service.refresh_access_token(refresh_token="original-refresh-token")

    assert tokens.access_token == "at-2"
    assert tokens.refresh_token == "original-refresh-token"
