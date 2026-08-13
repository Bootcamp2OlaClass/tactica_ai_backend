"""Unit tests for the extract_document task, run in Celery's eager mode
(synchronous, in-process) against a real database and a real
LocalStorageProvider (tmp_path), with a fake LLM provider standing in for
Gemini/OpenAI -- see test_process_document_task.py for the equivalent
Phase 05 pattern this mirrors.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.document import LLMExtractionStatus, ProcessingStatus
from app.models.extraction_candidate import CandidateStatus
from app.schemas.extraction import AcademicDocumentExtraction, ExtractedAssignment
from app.services.llm import LLMExtractionError, LLMTransientError
from app.services.storage.local import LocalStorageProvider
from app.worker.celery_app import celery_app
from app.worker.tasks import extraction as extraction_task_module
from app.worker.tasks.extraction import extract_document
from tests.conftest import TEST_DATABASE_URL
from tests.factories import create_document


@pytest.fixture
def eager_mode():
    original_eager = celery_app.conf.task_always_eager
    original_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager = original_eager
    celery_app.conf.task_eager_propagates = original_propagates


@pytest.fixture(autouse=True)
def task_session_local(monkeypatch):
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    test_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    monkeypatch.setattr(extraction_task_module, "SessionLocal", test_session_local)
    yield
    engine.dispose()


class FakeLLMProvider:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc

    def extract_structured(self, *, system_prompt, content, response_schema):
        if self.exc is not None:
            raise self.exc
        return self.response


@pytest.fixture
def local_storage_with_extracted_document(tmp_path, monkeypatch, db_session):
    provider = LocalStorageProvider(str(tmp_path))
    artifact_key = "courses/1/documents/stored.pdf.extracted.json"
    provider.save(
        json.dumps({"pages": [{"page_number": 1, "text": "CS101 syllabus text"}]}).encode(
            "utf-8"
        ),
        artifact_key,
    )

    document = create_document(db_session, processing_status=ProcessingStatus.COMPLETED)
    document.extracted_content_path = artifact_key
    db_session.commit()
    db_session.refresh(document)

    monkeypatch.setattr(
        "app.services.document_extraction.get_storage_provider", lambda settings: provider
    )

    return document


def _patch_provider(monkeypatch, provider):
    monkeypatch.setattr(
        "app.services.document_extraction.get_llm_provider", lambda settings: provider
    )


def test_successful_extraction_creates_candidates_and_completes(
    db_session, eager_mode, local_storage_with_extracted_document, monkeypatch
):
    document = local_storage_with_extracted_document
    response = AcademicDocumentExtraction(
        assignments=[ExtractedAssignment(title="HW1", source_page=1)]
    )
    _patch_provider(monkeypatch, FakeLLMProvider(response=response))

    result = extract_document.apply(args=[document.id])

    assert result.successful()
    assert result.result["status"] == "completed"
    assert result.result["candidate_count"] == 1

    db_session.refresh(document)
    assert document.llm_extraction_status == LLMExtractionStatus.COMPLETED
    assert document.llm_extraction_error is None

    candidates = document.extraction_candidates
    assert len(candidates) == 1
    assert candidates[0].status == CandidateStatus.PENDING
    assert candidates[0].payload["title"] == "HW1"


def test_document_not_ready_marks_failed_permanently(db_session, eager_mode, tmp_path, monkeypatch):
    provider = LocalStorageProvider(str(tmp_path))
    monkeypatch.setattr(
        "app.services.document_extraction.get_storage_provider", lambda settings: provider
    )
    document = create_document(db_session, processing_status=ProcessingStatus.UPLOADED)

    result = extract_document.apply(args=[document.id])

    assert result.failed()
    db_session.refresh(document)
    assert document.llm_extraction_status == LLMExtractionStatus.FAILED
    assert document.llm_extraction_error is not None


def test_llm_extraction_error_marks_failed_permanently(
    db_session, eager_mode, local_storage_with_extracted_document, monkeypatch
):
    document = local_storage_with_extracted_document
    _patch_provider(monkeypatch, FakeLLMProvider(exc=LLMExtractionError("bad output")))

    result = extract_document.apply(args=[document.id])

    assert result.failed()
    db_session.refresh(document)
    assert document.llm_extraction_status == LLMExtractionStatus.FAILED
    assert "did not produce usable output" in document.llm_extraction_error


def test_llm_transient_error_retries_then_fails_via_on_failure(
    db_session, eager_mode, local_storage_with_extracted_document, monkeypatch
):
    document = local_storage_with_extracted_document
    _patch_provider(monkeypatch, FakeLLMProvider(exc=LLMTransientError("timeout")))

    result = extract_document.apply(args=[document.id])

    assert result.failed()
    db_session.refresh(document)
    assert document.llm_extraction_status == LLMExtractionStatus.FAILED
    assert "repeated attempts" in document.llm_extraction_error


def test_already_completed_document_is_skipped_idempotently(db_session, eager_mode, tmp_path, monkeypatch):
    provider = LocalStorageProvider(str(tmp_path))
    monkeypatch.setattr(
        "app.services.document_extraction.get_storage_provider", lambda settings: provider
    )
    document = create_document(db_session, processing_status=ProcessingStatus.COMPLETED)
    document.llm_extraction_status = LLMExtractionStatus.COMPLETED
    db_session.commit()

    result = extract_document.apply(args=[document.id])

    assert result.successful()
    assert result.result["status"] == "skipped"


def test_deleted_document_is_skipped_without_error(db_session, eager_mode, tmp_path, monkeypatch):
    provider = LocalStorageProvider(str(tmp_path))
    monkeypatch.setattr(
        "app.services.document_extraction.get_storage_provider", lambda settings: provider
    )
    document = create_document(db_session)
    document.is_deleted = True
    db_session.commit()

    result = extract_document.apply(args=[document.id])

    assert result.successful()
    assert result.result["status"] == "skipped"


def test_nonexistent_document_is_skipped_without_error(db_session, eager_mode, tmp_path, monkeypatch):
    provider = LocalStorageProvider(str(tmp_path))
    monkeypatch.setattr(
        "app.services.document_extraction.get_storage_provider", lambda settings: provider
    )
    result = extract_document.apply(args=[999999])

    assert result.successful()
    assert result.result["status"] == "skipped"


def test_rerun_replaces_pending_candidates(
    db_session, eager_mode, local_storage_with_extracted_document, monkeypatch
):
    document = local_storage_with_extracted_document
    first_response = AcademicDocumentExtraction(
        assignments=[ExtractedAssignment(title="HW1", source_page=1)]
    )
    _patch_provider(monkeypatch, FakeLLMProvider(response=first_response))
    first_result = extract_document.apply(args=[document.id])
    assert first_result.successful()

    db_session.refresh(document)
    document.llm_extraction_status = LLMExtractionStatus.QUEUED
    db_session.commit()

    second_response = AcademicDocumentExtraction(
        assignments=[ExtractedAssignment(title="HW2", source_page=1)]
    )
    _patch_provider(monkeypatch, FakeLLMProvider(response=second_response))
    second_result = extract_document.apply(args=[document.id])
    assert second_result.successful()

    db_session.refresh(document)
    candidates = document.extraction_candidates
    assert len(candidates) == 1
    assert candidates[0].payload["title"] == "HW2"
