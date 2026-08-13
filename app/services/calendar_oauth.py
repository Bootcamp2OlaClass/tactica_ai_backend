"""Google OAuth (Calendar scope) — see PHASE_12_CALENDAR.md.

Independent of ADR-001's identity/login decision (that ADR covers this
app's own auth, not a third-party write-scope grant). NOT VERIFIED
against real Google endpoints: no OAuth credentials in this environment.
Exercised via an injectable `httpx.Client` test seam, same honesty
standard as every other provider in this codebase.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.services.calendar.exceptions import CalendarNotConfiguredError, CalendarTransientError

AUTHORIZATION_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: datetime


class CalendarOAuthService:
    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = http_client or httpx.Client(timeout=10.0)

    def _require_configured(self) -> None:
        if not (
            self.settings.google_calendar_client_id
            and self.settings.google_calendar_client_secret
            and self.settings.google_calendar_redirect_uri
        ):
            raise CalendarNotConfiguredError(
                "Google Calendar is not configured (set GOOGLE_CALENDAR_CLIENT_ID, "
                "GOOGLE_CALENDAR_CLIENT_SECRET, and GOOGLE_CALENDAR_REDIRECT_URI)."
            )

    def get_authorization_url(self, *, state: str) -> str:
        self._require_configured()
        params = {
            "client_id": self.settings.google_calendar_client_id,
            "redirect_uri": self.settings.google_calendar_redirect_uri,
            "response_type": "code",
            "scope": CALENDAR_SCOPE,
            "access_type": "offline",  # required to receive a refresh_token
            "prompt": "consent",
            "state": state,
        }
        return f"{AUTHORIZATION_BASE_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(self, *, code: str) -> TokenSet:
        self._require_configured()
        try:
            response = self._client.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.settings.google_calendar_client_id,
                    "client_secret": self.settings.google_calendar_client_secret,
                    "redirect_uri": self.settings.google_calendar_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        except httpx.HTTPError as exc:
            raise CalendarTransientError(f"Google token exchange failed: {exc}") from exc

        return self._parse_token_response(response)

    def refresh_access_token(self, *, refresh_token: str) -> TokenSet:
        self._require_configured()
        try:
            response = self._client.post(
                TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id": self.settings.google_calendar_client_id,
                    "client_secret": self.settings.google_calendar_client_secret,
                    "grant_type": "refresh_token",
                },
            )
        except httpx.HTTPError as exc:
            raise CalendarTransientError(f"Google token refresh failed: {exc}") from exc

        parsed = self._parse_token_response(response, fallback_refresh_token=refresh_token)
        return parsed

    def _parse_token_response(
        self, response: httpx.Response, *, fallback_refresh_token: str | None = None
    ) -> TokenSet:
        if response.status_code >= 500 or response.status_code == 429:
            raise CalendarTransientError(
                f"Google token endpoint returned a transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise CalendarTransientError(
                f"Google token endpoint rejected the request: {response.status_code} {response.text}"
            )

        body = response.json()
        expires_in = body.get("expires_in", 3600)
        return TokenSet(
            access_token=body["access_token"],
            # Google only returns refresh_token on the *first* consent;
            # subsequent refreshes must fall back to the one already on
            # file, per Google's own documented behavior.
            refresh_token=body.get("refresh_token") or fallback_refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        )
