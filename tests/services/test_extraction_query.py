from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.exceptions.document import DocumentNotFoundError
from app.services.extraction_query import ExtractionQueryService


def build_service(*, document=None):
    db = MagicMock()
    document_repository = MagicMock()
    document_repository.get_active_by_id.return_value = document
    candidate_repository = MagicMock()

    service = ExtractionQueryService(
        db=db,
        document_repository=document_repository,
        candidate_repository=candidate_repository,
    )
    return service, document_repository, candidate_repository


def test_list_candidates_document_not_found():
    service, _, _ = build_service(document=None)

    with pytest.raises(DocumentNotFoundError):
        service.list_candidates(document_id=1, user_id=1)


def test_list_candidates_not_owned(monkeypatch):
    document = SimpleNamespace(id=1, course_id=10)
    service, _, _ = build_service(document=document)
    monkeypatch.setattr(
        "app.services.extraction_query.course_repository.get_course_by_id",
        lambda **kwargs: None,
    )

    with pytest.raises(DocumentNotFoundError):
        service.list_candidates(document_id=1, user_id=999)


def test_list_candidates_returns_repository_results(monkeypatch):
    document = SimpleNamespace(id=1, course_id=10)
    service, _, candidate_repository = build_service(document=document)
    candidate_repository.list_by_document.return_value = ["candidate-a", "candidate-b"]
    monkeypatch.setattr(
        "app.services.extraction_query.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    result = service.list_candidates(document_id=1, user_id=1)

    assert result == ["candidate-a", "candidate-b"]
    candidate_repository.list_by_document.assert_called_once_with(1)
