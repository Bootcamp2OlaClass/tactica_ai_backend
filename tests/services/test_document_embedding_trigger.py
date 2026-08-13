from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.exceptions.document import DocumentNotFoundError
from app.exceptions.rag import (
    ChunkEmbeddingAlreadyInProgressError,
    DocumentNotReadyForEmbeddingError,
    EmbeddingNotAvailableError,
)
from app.models.document import ChunkEmbeddingStatus, ProcessingStatus
from app.services.document_embedding_trigger import DocumentEmbeddingTriggerService


def build_service(*, document=None):
    db = MagicMock()
    repository = MagicMock()
    repository.get_active_by_id.return_value = document

    service = DocumentEmbeddingTriggerService(db=db, document_repository=repository)
    return service, repository


def test_trigger_document_not_found():
    service, _ = build_service(document=None)

    with pytest.raises(DocumentNotFoundError):
        service.trigger_embedding(document_id=1, user_id=1)


def test_trigger_not_owned(monkeypatch):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        processing_status=ProcessingStatus.COMPLETED,
        chunk_embedding_status=ChunkEmbeddingStatus.NOT_REQUESTED,
    )
    service, _ = build_service(document=document)
    monkeypatch.setattr(
        "app.services.document_embedding_trigger.course_repository.get_course_by_id",
        lambda **kwargs: None,
    )

    with pytest.raises(DocumentNotFoundError):
        service.trigger_embedding(document_id=1, user_id=999)


@pytest.mark.parametrize(
    "processing_status",
    [ProcessingStatus.UPLOADED, ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING, ProcessingStatus.FAILED],
)
def test_trigger_requires_processing_completed(monkeypatch, processing_status):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        processing_status=processing_status,
        chunk_embedding_status=ChunkEmbeddingStatus.NOT_REQUESTED,
    )
    service, repository = build_service(document=document)
    monkeypatch.setattr(
        "app.services.document_embedding_trigger.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    with pytest.raises(DocumentNotReadyForEmbeddingError):
        service.trigger_embedding(document_id=1, user_id=1)

    repository.mark_chunk_embedding_queued.assert_not_called()


@pytest.mark.parametrize(
    "chunk_status",
    [ChunkEmbeddingStatus.PROCESSING, ChunkEmbeddingStatus.COMPLETED],
)
def test_trigger_not_allowed_in_certain_statuses(monkeypatch, chunk_status):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        processing_status=ProcessingStatus.COMPLETED,
        chunk_embedding_status=chunk_status,
    )
    service, repository = build_service(document=document)
    monkeypatch.setattr(
        "app.services.document_embedding_trigger.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    with pytest.raises(ChunkEmbeddingAlreadyInProgressError):
        service.trigger_embedding(document_id=1, user_id=1)

    repository.mark_chunk_embedding_queued.assert_not_called()


@pytest.mark.parametrize(
    "chunk_status",
    [ChunkEmbeddingStatus.NOT_REQUESTED, ChunkEmbeddingStatus.QUEUED, ChunkEmbeddingStatus.FAILED],
)
def test_trigger_succeeds_from_embeddable_statuses(monkeypatch, chunk_status):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        processing_status=ProcessingStatus.COMPLETED,
        chunk_embedding_status=chunk_status,
    )
    service, repository = build_service(document=document)
    repository.mark_chunk_embedding_queued.return_value = document
    monkeypatch.setattr(
        "app.services.document_embedding_trigger.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )
    enqueue_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.document_embedding_trigger.embed_document.delay", enqueue_mock
    )

    result = service.trigger_embedding(document_id=1, user_id=1)

    assert result is document
    enqueue_mock.assert_called_once_with(document.id)
    repository.mark_chunk_embedding_queued.assert_called_once_with(document)


def test_trigger_enqueue_failure_raises_unavailable(monkeypatch):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        processing_status=ProcessingStatus.COMPLETED,
        chunk_embedding_status=ChunkEmbeddingStatus.NOT_REQUESTED,
    )
    service, repository = build_service(document=document)
    monkeypatch.setattr(
        "app.services.document_embedding_trigger.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )
    monkeypatch.setattr(
        "app.services.document_embedding_trigger.embed_document.delay",
        MagicMock(side_effect=ConnectionError("broker unreachable")),
    )

    with pytest.raises(EmbeddingNotAvailableError):
        service.trigger_embedding(document_id=1, user_id=1)

    repository.mark_chunk_embedding_queued.assert_not_called()
