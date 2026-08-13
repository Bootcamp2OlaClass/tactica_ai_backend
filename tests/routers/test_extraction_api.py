from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.exceptions.document import DocumentNotFoundError
from app.exceptions.extraction import (
    DocumentNotReadyForExtractionError,
    ExtractionAlreadyInProgressError,
    ExtractionCandidateAlreadyReviewedError,
    ExtractionCandidateNotFoundError,
    ExtractionNotAvailableError,
)
from app.main import app
from app.models.document import (
    ChunkEmbeddingStatus,
    DocumentType,
    ExtractionMethod,
    LLMExtractionStatus,
    ProcessingStatus,
)
from app.models.extraction_candidate import CandidateStatus, CandidateType
from app.routers.extraction import (
    get_document_extraction_trigger_service,
    get_extraction_query_service,
    get_extraction_review_service,
)
from app.services.document_extraction_trigger import DocumentExtractionTriggerService
from app.services.extraction_query import ExtractionQueryService
from app.services.extraction_review import ExtractionReviewService


def make_document(**overrides):
    defaults = dict(
        id=1,
        course_id=10,
        uploaded_by=42,
        original_file_name="syllabus.pdf",
        mime_type="application/pdf",
        file_size=1024,
        checksum="abc",
        document_type=DocumentType.SYLLABUS,
        processing_status=ProcessingStatus.COMPLETED,
        processing_error=None,
        processed_at=None,
        extraction_method=ExtractionMethod.NATIVE,
        page_count=1,
        text_length=100,
        llm_extraction_status=LLMExtractionStatus.QUEUED,
        llm_extraction_error=None,
        chunk_embedding_status=ChunkEmbeddingStatus.NOT_REQUESTED,
        chunk_embedding_error=None,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_candidate(**overrides):
    defaults = dict(
        id=1,
        document_id=1,
        candidate_type=CandidateType.ASSIGNMENT,
        payload={"title": "HW1"},
        source_page=1,
        status=CandidateStatus.PENDING,
        created_task_id=None,
        reviewed_at=None,
        reviewed_by=None,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def trigger_service() -> MagicMock:
    return MagicMock(spec=DocumentExtractionTriggerService)


@pytest.fixture
def query_service() -> MagicMock:
    return MagicMock(spec=ExtractionQueryService)


@pytest.fixture
def review_service() -> MagicMock:
    return MagicMock(spec=ExtractionReviewService)


@pytest.fixture
def client(trigger_service, query_service, review_service):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=42)
    app.dependency_overrides[get_document_extraction_trigger_service] = lambda: trigger_service
    app.dependency_overrides[get_extraction_query_service] = lambda: query_service
    app.dependency_overrides[get_extraction_review_service] = lambda: review_service
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def test_trigger_extraction_requires_authentication(trigger_service):
    app.dependency_overrides[get_document_extraction_trigger_service] = lambda: trigger_service
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.post("/api/v1/documents/1/extract")

    test_client.close()
    app.dependency_overrides.clear()
    assert response.status_code == 401
    trigger_service.trigger_extraction.assert_not_called()


def test_trigger_extraction_success_returns_202(client, trigger_service):
    trigger_service.trigger_extraction.return_value = make_document()

    response = client.post("/api/v1/documents/1/extract")

    assert response.status_code == 202
    trigger_service.trigger_extraction.assert_called_once_with(document_id=1, user_id=42)
    assert response.json()["llm_extraction_status"] == "QUEUED"


def test_trigger_extraction_not_found_returns_404(client, trigger_service):
    trigger_service.trigger_extraction.side_effect = DocumentNotFoundError("nope")

    response = client.post("/api/v1/documents/1/extract")

    assert response.status_code == 404


def test_trigger_extraction_not_ready_returns_409(client, trigger_service):
    trigger_service.trigger_extraction.side_effect = DocumentNotReadyForExtractionError("not ready")

    response = client.post("/api/v1/documents/1/extract")

    assert response.status_code == 409


def test_trigger_extraction_in_progress_returns_409(client, trigger_service):
    trigger_service.trigger_extraction.side_effect = ExtractionAlreadyInProgressError("already running")

    response = client.post("/api/v1/documents/1/extract")

    assert response.status_code == 409


def test_trigger_extraction_unavailable_returns_503(client, trigger_service):
    trigger_service.trigger_extraction.side_effect = ExtractionNotAvailableError("no provider")

    response = client.post("/api/v1/documents/1/extract")

    assert response.status_code == 503


def test_list_candidates_returns_items(client, query_service):
    query_service.list_candidates.return_value = [make_candidate(), make_candidate(id=2)]

    response = client.get("/api/v1/documents/1/extraction-candidates")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["items"][0]["candidate_type"] == "ASSIGNMENT"
    query_service.list_candidates.assert_called_once_with(document_id=1, user_id=42)


def test_list_candidates_not_found_returns_404(client, query_service):
    query_service.list_candidates.side_effect = DocumentNotFoundError("nope")

    response = client.get("/api/v1/documents/1/extraction-candidates")

    assert response.status_code == 404


def test_accept_candidate_success(client, review_service):
    review_service.accept.return_value = make_candidate(status=CandidateStatus.ACCEPTED)

    response = client.post("/api/v1/extraction-candidates/1/accept")

    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    review_service.accept.assert_called_once_with(candidate_id=1, user_id=42)


def test_accept_candidate_not_found_returns_404(client, review_service):
    review_service.accept.side_effect = ExtractionCandidateNotFoundError("nope")

    response = client.post("/api/v1/extraction-candidates/1/accept")

    assert response.status_code == 404


def test_accept_candidate_already_reviewed_returns_409(client, review_service):
    review_service.accept.side_effect = ExtractionCandidateAlreadyReviewedError("already reviewed")

    response = client.post("/api/v1/extraction-candidates/1/accept")

    assert response.status_code == 409


def test_reject_candidate_success(client, review_service):
    review_service.reject.return_value = make_candidate(status=CandidateStatus.REJECTED)

    response = client.post("/api/v1/extraction-candidates/1/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    review_service.reject.assert_called_once_with(candidate_id=1, user_id=42)
