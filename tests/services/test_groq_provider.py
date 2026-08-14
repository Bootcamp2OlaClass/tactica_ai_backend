"""Unit tests for GroqProvider against a fake OpenAI-SDK-shaped client --
same "no live network calls in the suite" standard as OpenAIProvider/
GeminiProvider (see their own docstrings), and the same reason: Groq's API
is OpenAI-compatible, but its structured-output support is inconsistent, so
this provider deliberately uses `.create()` + manual JSON-mode parsing
instead of `.parse()` (see app/services/llm/groq_provider.py's docstring)."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.services.llm.exceptions import LLMExtractionError, LLMTransientError
from app.services.llm.groq_provider import GroqProvider


class _Answer(BaseModel):
    text: str
    confident: bool


def _fake_completion(content: str | None):
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


class FakeGroqClient:
    def __init__(self, content: str | None = None, raise_exc: Exception | None = None):
        self._content = content
        self._raise_exc = raise_exc
        self.last_kwargs: dict | None = None
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._raise_exc is not None:
            raise self._raise_exc
        return _fake_completion(self._content)


def test_extract_structured_parses_valid_json_response():
    client = FakeGroqClient(content='{"text": "Friday", "confident": true}')
    provider = GroqProvider(api_key="fake-key", model="llama-3.3-70b-versatile", client=client)

    result = provider.extract_structured(
        system_prompt="Answer the question.",
        content="When is the exam?",
        response_schema=_Answer,
    )

    assert isinstance(result, _Answer)
    assert result.text == "Friday"
    assert result.confident is True
    # JSON mode requested, not OpenAI's strict-schema .parse() convenience.
    assert client.last_kwargs["response_format"] == {"type": "json_object"}
    assert "json schema" in client.last_kwargs["messages"][0]["content"].lower()


def test_extract_structured_raises_transient_error_on_request_failure():
    client = FakeGroqClient(raise_exc=RuntimeError("connection reset"))
    provider = GroqProvider(api_key="fake-key", model="llama-3.3-70b-versatile", client=client)

    with pytest.raises(LLMTransientError):
        provider.extract_structured(
            system_prompt="Answer.", content="Hi", response_schema=_Answer
        )


def test_extract_structured_raises_extraction_error_on_empty_content():
    client = FakeGroqClient(content=None)
    provider = GroqProvider(api_key="fake-key", model="llama-3.3-70b-versatile", client=client)

    with pytest.raises(LLMExtractionError):
        provider.extract_structured(
            system_prompt="Answer.", content="Hi", response_schema=_Answer
        )


def test_extract_structured_raises_extraction_error_on_schema_mismatch():
    client = FakeGroqClient(content='{"unexpected": "shape"}')
    provider = GroqProvider(api_key="fake-key", model="llama-3.3-70b-versatile", client=client)

    with pytest.raises(LLMExtractionError):
        provider.extract_structured(
            system_prompt="Answer.", content="Hi", response_schema=_Answer
        )
