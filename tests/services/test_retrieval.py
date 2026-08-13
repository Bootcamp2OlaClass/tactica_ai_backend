"""RetrievalService-level tests -- the full query-embedding + search path,
with a fake embedding provider standing in for Gemini/OpenAI. The SQL-level
isolation proof itself lives in tests/test_document_chunk_repository.py;
these tests confirm RetrievalService wires user_id through correctly end
to end and never accepts it as optional.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.exceptions.rag import EmbeddingNotAvailableError
from app.models.document_chunk import DocumentChunk
from app.services.retrieval import RetrievalService
from tests.factories import create_document_with_owner


class FakeEmbeddingProvider:
    model = "fake-embedding-model"

    def __init__(self, vector=None):
        self._vector = vector or [0.5] * 768
        self.queries: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.queries.extend(texts)
        return [self._vector for _ in texts]


def _add_chunk(db_session, *, document, user_id, content, embedding, chunk_index=0):
    chunk = DocumentChunk(
        document_id=document.id,
        course_id=document.course_id,
        user_id=user_id,
        chunk_index=chunk_index,
        content=content,
        start_page=1,
        end_page=1,
        embedding=embedding,
        embedding_model="fake/test-model",
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


def test_search_requires_user_id_keyword_argument():
    # user_id has no default -- calling without it is a TypeError, not a
    # silently-broader query. Documents the contract at the type level.
    service = RetrievalService(
        db=MagicMock(),
        settings=SimpleNamespace(llm_provider="gemini"),
        embedding_provider=FakeEmbeddingProvider(),
    )
    with pytest.raises(TypeError):
        service.search(query="anything")


def test_search_raises_when_provider_not_configured(monkeypatch):
    service = RetrievalService(
        db=MagicMock(),
        settings=SimpleNamespace(llm_provider=None),
        embedding_provider=None,
    )
    monkeypatch.setattr(
        service,
        "_get_embedding_provider",
        MagicMock(side_effect=EmbeddingNotAvailableError("not configured")),
    )

    with pytest.raises(EmbeddingNotAvailableError):
        service.search(user_id=1, query="anything")


def test_search_returns_only_the_requesting_users_chunks(db_session):
    document_a, user_a = create_document_with_owner(db_session, email_prefix="retr-a")
    document_b, user_b = create_document_with_owner(db_session, email_prefix="retr-b")

    shared_vector = [0.5] * 768
    _add_chunk(db_session, document=document_a, user_id=user_a.id, content="A's chunk", embedding=shared_vector)
    _add_chunk(db_session, document=document_b, user_id=user_b.id, content="B's chunk", embedding=shared_vector)

    provider = FakeEmbeddingProvider(vector=shared_vector)
    service = RetrievalService(
        db=db_session,
        settings=SimpleNamespace(llm_provider="gemini"),
        embedding_provider=provider,
    )

    results = service.search(user_id=user_a.id, query="what's the exam date?", top_k=10)

    assert len(results) == 1
    assert results[0].content == "A's chunk"
    assert provider.queries == ["what's the exam date?"]


def test_search_result_carries_full_provenance(db_session):
    document, user = create_document_with_owner(db_session, email_prefix="prov")
    vector = [0.3] * 768
    chunk = _add_chunk(db_session, document=document, user_id=user.id, content="Provenance check", embedding=vector)

    provider = FakeEmbeddingProvider(vector=vector)
    service = RetrievalService(
        db=db_session,
        settings=SimpleNamespace(llm_provider="gemini"),
        embedding_provider=provider,
    )

    results = service.search(user_id=user.id, query="anything", top_k=5)

    assert len(results) == 1
    result = results[0]
    assert result.chunk_id == chunk.id
    assert result.document_id == document.id
    assert result.course_id == document.course_id
    assert result.start_page == 1
    assert result.end_page == 1
