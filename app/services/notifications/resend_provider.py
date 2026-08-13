"""Resend implementation of NotificationProvider — see
PHASE_13_NOTIFICATIONS.md.

NOT VERIFIED against the real Resend API: no API key was available in
this environment. Exercised only via a fake-provider/httpx.MockTransport
test seam, same honesty standard as every other provider in this
codebase. Uses `httpx` directly against Resend's REST API rather than
Resend's own SDK, for the same dependency-footprint reasoning as Phase
12's GoogleCalendarProvider.
"""

import httpx

from app.services.notifications.base import NotificationProvider
from app.services.notifications.exceptions import (
    NotificationProviderError,
    NotificationTransientError,
)

RESEND_API_BASE = "https://api.resend.com"


class ResendProvider(NotificationProvider):
    def __init__(
        self, *, api_key: str, from_address: str, client: httpx.Client | None = None
    ) -> None:
        self.from_address = from_address
        self._api_key = api_key
        self._client = client or httpx.Client(base_url=RESEND_API_BASE, timeout=10.0)

    def send_email(self, *, to: str, subject: str, body: str) -> str:
        try:
            response = self._client.post(
                "/emails",
                json={
                    "from": self.from_address,
                    "to": [to],
                    "subject": subject,
                    "html": body,
                },
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            raise NotificationTransientError(f"Resend request failed: {exc}") from exc

        if response.status_code >= 500 or response.status_code == 429:
            raise NotificationTransientError(
                f"Resend returned a transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise NotificationProviderError(
                f"Resend rejected the email: {response.status_code} {response.text}"
            )

        message_id = response.json().get("id")
        if not message_id:
            raise NotificationProviderError("Resend did not return a message id.")
        return message_id
