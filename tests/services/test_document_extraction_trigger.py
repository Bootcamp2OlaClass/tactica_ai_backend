from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.exceptions.document import DocumentNotFoundError
from app.exceptions.extraction import (
    DocumentNotReadyForExtractionError,
    ExtractionAlreadyInProgressError,
    ExtractionNotAvailableError,
)
from app.models.document import LLMExtractionStatus, ProcessingStatus
from app.services.document_extraction_trigger import DocumentExtractionTriggerService


def build_service(*, document=None):
    db = MagicMock()
    repository = MagicMock()
    repository.get_active_by_id.return_value = document

    service = DocumentExtractionTriggerService(db=db, document_repository=repository)
    return service, repository


def test_trigger_document_not_found():
    service, _ = build_service(document=None)

    with pytest.raises(DocumentNotFoundError):
        service.trigger_extraction(document_id=1, user_id=1)


def test_trigger_not_owned(monkeypatch):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        processing_status=ProcessingStatus.COMPLETED,
        llm_extraction_status=LLMExtractionStatus.NOT_REQUESTED,
    )
    service, _ = build_service(document=document)
    monkeypatch.setattr(
        "app.services.document_extraction_trigger.course_repository.get_course_by_id",
        lambda **kwargs: None,
    )

    with pytest.raises(DocumentNotFoundError):
        service.trigger_extraction(document_id=1, user_id=999)


@pytest.mark.parametrize(
    "processing_status",
    [ProcessingStatus.UPLOADED, ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING, ProcessingStatus.FAILED],
)
def test_trigger_requires_processing_completed(monkeypatch, processing_status):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        processing_status=processing_status,
        llm_extraction_status=LLMExtractionStatus.NOT_REQUESTED,
    )
    service, repository = build_service(document=document)
    monkeypatch.setattr(
        "app.services.document_extraction_trigger.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    with pytest.raises(DocumentNotReadyForExtractionError):
        service.trigger_extraction(document_id=1, user_id=1)

    repository.mark_extraction_queued.assert_not_called()


@pytest.mark.parametrize(
    "llm_status",
    [LLMExtractionStatus.PROCESSING, LLMExtractionStatus.COMPLETED],
)
def test_trigger_not_allowed_in_certain_extraction_statuses(monkeypatch, llm_status):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        processing_status=ProcessingStatus.COMPLETED,
        llm_extraction_status=llm_status,
    )
    service, repository = build_service(document=document)
    monkeypatch.setattr(
        "app.services.document_extraction_trigger.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    with pytest.raises(ExtractionAlreadyInProgressError):
        service.trigger_extraction(document_id=1, user_id=1)

    repository.mark_extraction_queued.assert_not_called()


@pytest.mark.parametrize(
    "llm_status",
    [LLMExtractionStatus.NOT_REQUESTED, LLMExtractionStatus.QUEUED, LLMExtractionStatus.FAILED],
)
def test_trigger_succeeds_from_extractable_statuses(monkeypatch, llm_status):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        processing_status=ProcessingStatus.COMPLETED,
        llm_extraction_status=llm_status,
    )
    service, repository = build_service(document=document)
    repository.mark_extraction_queued.return_value = document
    monkeypatch.setattr(
        "app.services.document_extraction_trigger.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )
    enqueue_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.document_extraction_trigger.extract_document.delay", enqueue_mock
    )

    result = service.trigger_extraction(document_id=1, user_id=1)

    assert result is document
    enqueue_mock.assert_called_once_with(document.id)
    repository.mark_extraction_queued.assert_called_once_with(document)


def test_trigger_enqueue_failure_raises_unavailable(monkeypatch):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        processing_status=ProcessingStatus.COMPLETED,
        llm_extraction_status=LLMExtractionStatus.NOT_REQUESTED,
    )
    service, repository = build_service(document=document)
    monkeypatch.setattr(
        "app.services.document_extraction_trigger.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )
    monkeypatch.setattr(
        "app.services.document_extraction_trigger.extract_document.delay",
        MagicMock(side_effect=ConnectionError("broker unreachable")),
    )

    with pytest.raises(ExtractionNotAvailableError):
        service.trigger_extraction(document_id=1, user_id=1)

    repository.mark_extraction_queued.assert_not_called()
