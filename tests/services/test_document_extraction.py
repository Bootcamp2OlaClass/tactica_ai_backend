import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.exceptions.extraction import (
    DocumentNotReadyForExtractionError,
    ExtractionNotAvailableError,
)
from app.models.document import ProcessingStatus
from app.models.extraction_candidate import CandidateType
from app.schemas.extraction import (
    AcademicDocumentExtraction,
    ExtractedAssignment,
    ExtractedCourseInfo,
)
from app.services.document_extraction import DocumentExtractionService
from app.services.llm import LLMNotConfiguredError


class FakeLLMProvider:
    def __init__(self, response: AcademicDocumentExtraction):
        self.response = response
        self.calls = []

    def extract_structured(self, *, system_prompt, content, response_schema):
        self.calls.append({"system_prompt": system_prompt, "content": content})
        return self.response


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


def build_service(*, llm_provider=None, storage_service=None):
    db = MagicMock()
    candidate_repository = MagicMock()
    candidate_repository.create.side_effect = (
        lambda **kwargs: SimpleNamespace(**kwargs)
    )
    service = DocumentExtractionService(
        db=db,
        settings=MagicMock(),
        candidate_repository=candidate_repository,
        storage_service=storage_service,
        llm_provider=llm_provider,
    )
    return service, db, candidate_repository


def test_extract_raises_when_processing_not_completed():
    service, _, _ = build_service(llm_provider=FakeLLMProvider(AcademicDocumentExtraction()))
    document = build_document(processing_status=ProcessingStatus.PROCESSING)

    with pytest.raises(DocumentNotReadyForExtractionError):
        service.extract(document)


def test_extract_raises_when_no_extracted_content_path():
    service, _, _ = build_service(llm_provider=FakeLLMProvider(AcademicDocumentExtraction()))
    document = build_document(extracted_content_path=None)

    with pytest.raises(DocumentNotReadyForExtractionError):
        service.extract(document)


def test_extract_raises_when_llm_not_configured(monkeypatch):
    service, _, _ = build_service(llm_provider=None)
    monkeypatch.setattr(
        service,
        "_get_llm_provider",
        MagicMock(side_effect=ExtractionNotAvailableError("not configured")),
    )
    document = build_document()

    with pytest.raises(ExtractionNotAvailableError):
        service.extract(document)


def test_extract_creates_one_candidate_per_entity():
    extraction = AcademicDocumentExtraction(
        course=ExtractedCourseInfo(course_name="CS101", source_page=1),
        assignments=[ExtractedAssignment(title="HW1", source_page=2)],
    )
    provider = FakeLLMProvider(extraction)
    storage = FakeStorage([{"page_number": 1, "text": "CS101 syllabus"}])
    service, db, candidate_repository = build_service(
        llm_provider=provider, storage_service=storage
    )
    document = build_document()

    created = service.extract(document)

    assert len(created) == 2
    candidate_repository.delete_pending_for_document.assert_called_once_with(document.id)
    db.commit.assert_called_once()

    call_kwargs = [call.kwargs for call in candidate_repository.create.call_args_list]
    types = {kwargs["candidate_type"] for kwargs in call_kwargs}
    assert types == {CandidateType.COURSE_INFO, CandidateType.ASSIGNMENT}


def test_extract_passes_page_labeled_content_to_provider():
    provider = FakeLLMProvider(AcademicDocumentExtraction())
    storage = FakeStorage(
        [
            {"page_number": 1, "text": "first page text"},
            {"page_number": 2, "text": "second page text"},
        ]
    )
    service, _, _ = build_service(llm_provider=provider, storage_service=storage)
    document = build_document()

    service.extract(document)

    assert len(provider.calls) == 1
    content = provider.calls[0]["content"]
    assert "[Page 1]\nfirst page text" in content
    assert "[Page 2]\nsecond page text" in content


def test_extract_with_no_entities_creates_no_candidates():
    provider = FakeLLMProvider(AcademicDocumentExtraction())
    storage = FakeStorage([{"page_number": 1, "text": "nothing useful"}])
    service, db, candidate_repository = build_service(
        llm_provider=provider, storage_service=storage
    )
    document = build_document()

    created = service.extract(document)

    assert created == []
    candidate_repository.create.assert_not_called()
    db.commit.assert_called_once()
