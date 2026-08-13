from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.exceptions.document import (
    DocumentNotFoundError,
    DocumentProcessingUnavailableError,
    DocumentReprocessNotAllowedError,
)
from app.models.document import ProcessingStatus
from app.services.document_reprocess import DocumentReprocessService


def build_service(*, document=None):
    db = MagicMock()
    repository = MagicMock()
    repository.get_active_by_id.return_value = document

    service = DocumentReprocessService(db=db, document_repository=repository)
    return service, repository


def test_reprocess_document_not_found():
    service, repository = build_service(document=None)

    with pytest.raises(DocumentNotFoundError):
        service.reprocess_document(document_id=1, user_id=1)


def test_reprocess_document_not_owned(monkeypatch):
    document = SimpleNamespace(id=1, course_id=10, processing_status=ProcessingStatus.FAILED)
    service, repository = build_service(document=document)

    monkeypatch.setattr(
        "app.services.document_reprocess.course_repository.get_course_by_id",
        lambda **kwargs: None,
    )

    with pytest.raises(DocumentNotFoundError):
        service.reprocess_document(document_id=1, user_id=999)


@pytest.mark.parametrize(
    "status",
    [ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING, ProcessingStatus.COMPLETED],
)
def test_reprocess_document_not_allowed_in_certain_statuses(monkeypatch, status):
    document = SimpleNamespace(id=1, course_id=10, processing_status=status)
    service, repository = build_service(document=document)

    monkeypatch.setattr(
        "app.services.document_reprocess.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    with pytest.raises(DocumentReprocessNotAllowedError):
        service.reprocess_document(document_id=1, user_id=1)

    repository.mark_queued.assert_not_called()


@pytest.mark.parametrize("status", [ProcessingStatus.UPLOADED, ProcessingStatus.FAILED])
def test_reprocess_document_succeeds_from_reprocessable_statuses(monkeypatch, status):
    document = SimpleNamespace(id=1, course_id=10, processing_status=status)
    service, repository = build_service(document=document)
    repository.mark_queued.return_value = document

    monkeypatch.setattr(
        "app.services.document_reprocess.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    enqueue_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.document_reprocess.process_document.delay", enqueue_mock
    )

    result = service.reprocess_document(document_id=1, user_id=1)

    assert result is document
    enqueue_mock.assert_called_once_with(document.id)
    repository.mark_queued.assert_called_once_with(document)


def test_reprocess_document_enqueue_failure_raises_unavailable(monkeypatch):
    document = SimpleNamespace(id=1, course_id=10, processing_status=ProcessingStatus.FAILED)
    service, repository = build_service(document=document)

    monkeypatch.setattr(
        "app.services.document_reprocess.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    monkeypatch.setattr(
        "app.services.document_reprocess.process_document.delay",
        MagicMock(side_effect=ConnectionError("broker unreachable")),
    )

    with pytest.raises(DocumentProcessingUnavailableError):
        service.reprocess_document(document_id=1, user_id=1)

    repository.mark_queued.assert_not_called()
