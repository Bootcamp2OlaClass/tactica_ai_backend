"""ResendProvider tests -- see PHASE_13_NOTIFICATIONS.md.

Exercises the real REST client code path against httpx.MockTransport --
NOT VERIFIED against the real Resend API, no credentials in this
environment, same honesty standard as every other provider.
"""

import httpx
import pytest

from app.services.notifications.exceptions import (
    NotificationProviderError,
    NotificationTransientError,
)
from app.services.notifications.resend_provider import RESEND_API_BASE, ResendProvider


def _provider_with(handler) -> ResendProvider:
    client = httpx.Client(base_url=RESEND_API_BASE, transport=httpx.MockTransport(handler))
    return ResendProvider(api_key="key-1", from_address="coach@tactica.ai", client=client)


def test_send_email_returns_the_providers_message_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer key-1"
        assert request.url.path == "/emails"
        return httpx.Response(200, json={"id": "resend-msg-1"})

    provider = _provider_with(handler)

    message_id = provider.send_email(to="student@example.com", subject="Hi", body="<p>Hi</p>")

    assert message_id == "resend-msg-1"


def test_send_email_raises_transient_error_on_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    provider = _provider_with(handler)

    with pytest.raises(NotificationTransientError):
        provider.send_email(to="student@example.com", subject="Hi", body="<p>Hi</p>")


def test_send_email_raises_provider_error_on_rejection():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="invalid recipient")

    provider = _provider_with(handler)

    with pytest.raises(NotificationProviderError):
        provider.send_email(to="not-an-email", subject="Hi", body="<p>Hi</p>")
