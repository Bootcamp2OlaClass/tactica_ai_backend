import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.exceptions.chat import ChatNotAvailableError, ConversationNotFoundError
from app.main import app
from app.models.message import MessageRole
from app.routers.chat import chat_rate_limit, get_chat_query_service, get_chat_service
from app.services.chat import ChatService
from app.services.chat_query import ChatQueryService
from app.services.llm import LLMExtractionError, LLMTransientError


def make_conversation(**overrides):
    defaults = dict(
        id=1,
        user_id=42,
        title="When is my exam?",
        created_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_message(**overrides):
    defaults = dict(
        id=1,
        conversation_id=1,
        role=MessageRole.ASSISTANT,
        content="Your exam is Friday.",
        grounded=True,
        citations=[{"chunk_id": 5, "document_id": 9}],
        created_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def chat_service() -> MagicMock:
    return MagicMock(spec=ChatService)


@pytest.fixture
def chat_query_service() -> MagicMock:
    return MagicMock(spec=ChatQueryService)


@pytest.fixture
def client(chat_service, chat_query_service):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=42)
    app.dependency_overrides[get_chat_service] = lambda: chat_service
    app.dependency_overrides[get_chat_query_service] = lambda: chat_query_service
    # This file tests chat *logic* against a mocked service, not the rate
    # limiter (that has its own coverage in test_rate_limiting.py) --
    # without this override every test here would share one Redis counter
    # keyed by the fixed user id=42 override above.
    app.dependency_overrides[chat_rate_limit] = lambda: None
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def test_send_chat_message_requires_authentication(chat_service):
    app.dependency_overrides[get_chat_service] = lambda: chat_service
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.post("/api/v1/chat", json={"message": "hi"})

    test_client.close()
    app.dependency_overrides.clear()
    assert response.status_code == 401
    chat_service.send_message.assert_not_called()


def test_send_chat_message_success_returns_200(client, chat_service):
    conversation = make_conversation()
    message = make_message()
    chat_service.send_message.return_value = (conversation, message)

    response = client.post("/api/v1/chat", json={"message": "When is my exam?"})

    assert response.status_code == 200
    body = response.json()
    assert body["conversation"]["id"] == conversation.id
    assert body["message"]["content"] == "Your exam is Friday."
    assert body["message"]["citations"] == [{"chunk_id": 5, "document_id": 9}]
    chat_service.send_message.assert_called_once_with(
        user_id=42,
        message="When is my exam?",
        conversation_id=None,
        course_id=None,
    )


def test_send_chat_message_passes_conversation_and_course_id(client, chat_service):
    chat_service.send_message.return_value = (make_conversation(), make_message())

    client.post(
        "/api/v1/chat",
        json={"message": "Follow-up", "conversation_id": 7, "course_id": 3},
    )

    chat_service.send_message.assert_called_once_with(
        user_id=42, message="Follow-up", conversation_id=7, course_id=3
    )


def test_send_chat_message_conversation_not_found_returns_404(client, chat_service):
    chat_service.send_message.side_effect = ConversationNotFoundError("nope")

    response = client.post(
        "/api/v1/chat", json={"message": "hi", "conversation_id": 999}
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "error",
    [
        ChatNotAvailableError("no provider"),
        LLMTransientError("rate limited"),
        LLMExtractionError("bad schema"),
    ],
)
def test_send_chat_message_provider_failures_return_503(client, chat_service, error):
    chat_service.send_message.side_effect = error

    response = client.post("/api/v1/chat", json={"message": "hi"})

    assert response.status_code == 503


def test_send_chat_message_rejects_empty_message(client, chat_service):
    response = client.post("/api/v1/chat", json={"message": ""})

    assert response.status_code == 422
    chat_service.send_message.assert_not_called()


def test_stream_chat_message_emits_deltas_then_a_final_event(client, chat_service):
    conversation = make_conversation()
    message = make_message(content="Your exam is Friday.")
    chat_service.send_message.return_value = (conversation, message)

    with client.stream(
        "POST", "/api/v1/chat/stream", json={"message": "When is my exam?"}
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    events = [
        json.loads(line[len("data: ") :])
        for line in body.strip().split("\n\n")
        if line.startswith("data: ")
    ]

    *delta_events, final_event = events
    reconstructed = "".join(event["delta"] for event in delta_events)
    assert reconstructed == message.content

    assert final_event == {
        "done": True,
        "conversation_id": conversation.id,
        "message_id": message.id,
        "grounded": True,
        "citations": message.citations,
    }


def test_list_conversations_returns_only_the_services_result(client, chat_query_service):
    chat_query_service.list_conversations.return_value = [make_conversation()]

    response = client.get("/api/v1/chat/conversations")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    chat_query_service.list_conversations.assert_called_once_with(user_id=42)


def test_get_conversation_returns_messages(client, chat_query_service):
    conversation = make_conversation()
    messages = [
        make_message(role=MessageRole.USER, content="When is my exam?", grounded=None, citations=None),
        make_message(role=MessageRole.ASSISTANT),
    ]
    chat_query_service.get_conversation.return_value = (conversation, messages)

    response = client.get(f"/api/v1/chat/conversations/{conversation.id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "USER"
    assert body["messages"][1]["role"] == "ASSISTANT"


def test_get_conversation_not_found_returns_404(client, chat_query_service):
    chat_query_service.get_conversation.side_effect = ConversationNotFoundError("nope")

    response = client.get("/api/v1/chat/conversations/999")

    assert response.status_code == 404
