import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.exceptions.rag import (
    DocumentNotReadyForEmbeddingError,
    EmbeddingNotAvailableError,
)
from app.models.document import ProcessingStatus
from app.services.document_embedding import DocumentEmbeddingService


class FakeEmbeddingProvider:
    model = "fake-embedding-model"

    def __init__(self, vector_for=None):
        self._vector_for = vector_for or (lambda text: [0.1] * 768)
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [self._vector_for(text) for text in texts]


class FakeStorage:
    def __init__(self, pages: list[dict]):
        self._payload = json.dumps({"pages": pages}).encode("utf-8")

    def load(self, path):
        return self._payload


def build_document(**overrides):
    defaults = dict(
        id=1,
        course_id=10,
        processing_status=ProcessingStatus.COMPLETED,
        extracted_content_path="courses/10/documents/foo.extracted.json",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def build_service(*, embedding_provider=None, storage_service=None, owner_user_id=42):
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.scalar.return_value = (
        owner_user_id
    )

    chunk_repository = MagicMock()
    chunk_repository.bulk_create.side_effect = lambda chunks: [
        SimpleNamespace(**chunk) for chunk in chunks
    ]

    settings = SimpleNamespace(llm_provider="gemini")

    service = DocumentEmbeddingService(
        db=db,
        settings=settings,
        chunk_repository=chunk_repository,
        storage_service=storage_service or MagicMock(),
        embedding_provider=embedding_provider,
    )
    return service, db, chunk_repository


def test_embed_raises_when_processing_not_completed():
    service, _, _ = build_service(embedding_provider=FakeEmbeddingProvider())
    document = build_document(processing_status=ProcessingStatus.PROCESSING)

    with pytest.raises(DocumentNotReadyForEmbeddingError):
        service.embed(document)


def test_embed_raises_when_no_extracted_content_path():
    service, _, _ = build_service(embedding_provider=FakeEmbeddingProvider())
    document = build_document(extracted_content_path=None)

    with pytest.raises(DocumentNotReadyForEmbeddingError):
        service.embed(document)


def test_embed_raises_when_not_configured(monkeypatch):
    service, _, _ = build_service(embedding_provider=None)
    monkeypatch.setattr(
        service,
        "_get_embedding_provider",
        MagicMock(side_effect=EmbeddingNotAvailableError("not configured")),
    )
    document = build_document()

    with pytest.raises(EmbeddingNotAvailableError):
        service.embed(document)


def test_embed_creates_chunks_with_embeddings_and_provenance():
    provider = FakeEmbeddingProvider()
    storage = FakeStorage([{"page_number": 1, "text": "CS101 syllabus content here."}])
    service, db, chunk_repository = build_service(
        embedding_provider=provider, storage_service=storage, owner_user_id=42
    )
    document = build_document()

    created = service.embed(document)

    assert len(created) == 1
    chunk_repository.delete_by_document.assert_called_once_with(document.id)
    db.commit.assert_called_once()

    call_kwargs = chunk_repository.bulk_create.call_args[0][0]
    assert call_kwargs[0]["document_id"] == document.id
    assert call_kwargs[0]["course_id"] == document.course_id
    assert call_kwargs[0]["user_id"] == 42
    assert call_kwargs[0]["chunk_index"] == 0
    assert call_kwargs[0]["start_page"] == 1
    assert call_kwargs[0]["end_page"] == 1
    assert call_kwargs[0]["embedding"] == [0.1] * 768
    assert call_kwargs[0]["embedding_model"] == "gemini/fake-embedding-model"


def test_embed_with_empty_text_produces_no_chunks_but_still_commits():
    provider = FakeEmbeddingProvider()
    storage = FakeStorage([{"page_number": 1, "text": "   "}])
    service, db, chunk_repository = build_service(
        embedding_provider=provider, storage_service=storage
    )
    document = build_document()

    created = service.embed(document)

    assert created == []
    chunk_repository.delete_by_document.assert_called_once_with(document.id)
    chunk_repository.bulk_create.assert_not_called()
    db.commit.assert_called_once()
    assert provider.calls == []


def test_embed_rerun_replaces_existing_chunks():
    provider = FakeEmbeddingProvider()
    storage = FakeStorage([{"page_number": 1, "text": "Some syllabus text."}])
    service, db, chunk_repository = build_service(
        embedding_provider=provider, storage_service=storage
    )
    document = build_document()

    service.embed(document)
    service.embed(document)

    assert chunk_repository.delete_by_document.call_count == 2


def test_embed_passes_chunk_content_to_provider():
    provider = FakeEmbeddingProvider()
    storage = FakeStorage(
        [
            {"page_number": 1, "text": "Chunk content for embedding."},
        ]
    )
    service, _, _ = build_service(embedding_provider=provider, storage_service=storage)
    document = build_document()

    service.embed(document)

    assert len(provider.calls) == 1
    assert provider.calls[0] == ["Chunk content for embedding."]
