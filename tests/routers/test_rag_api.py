from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.exceptions.document import DocumentNotFoundError
from app.exceptions.rag import (
    ChunkEmbeddingAlreadyInProgressError,
    DocumentNotReadyForEmbeddingError,
    EmbeddingNotAvailableError,
)
from app.main import app
from app.models.document import (
    ChunkEmbeddingStatus,
    DocumentType,
    ExtractionMethod,
    LLMExtractionStatus,
    ProcessingStatus,
)
from app.routers.rag import get_document_embedding_trigger_service
from app.services.document_embedding_trigger import DocumentEmbeddingTriggerService


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
        llm_extraction_status=LLMExtractionStatus.NOT_REQUESTED,
        llm_extraction_error=None,
        chunk_embedding_status=ChunkEmbeddingStatus.QUEUED,
        chunk_embedding_error=None,
        created_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def trigger_service() -> MagicMock:
    return MagicMock(spec=DocumentEmbeddingTriggerService)


@pytest.fixture
def client(trigger_service):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=42)
    app.dependency_overrides[get_document_embedding_trigger_service] = lambda: trigger_service
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def test_trigger_embedding_requires_authentication(trigger_service):
    app.dependency_overrides[get_document_embedding_trigger_service] = lambda: trigger_service
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.post("/api/v1/documents/1/embed")

    test_client.close()
    app.dependency_overrides.clear()
    assert response.status_code == 401
    trigger_service.trigger_embedding.assert_not_called()


def test_trigger_embedding_success_returns_202(client, trigger_service):
    trigger_service.trigger_embedding.return_value = make_document()

    response = client.post("/api/v1/documents/1/embed")

    assert response.status_code == 202
    trigger_service.trigger_embedding.assert_called_once_with(document_id=1, user_id=42)
    assert response.json()["chunk_embedding_status"] == "QUEUED"


def test_trigger_embedding_not_found_returns_404(client, trigger_service):
    trigger_service.trigger_embedding.side_effect = DocumentNotFoundError("nope")

    response = client.post("/api/v1/documents/1/embed")

    assert response.status_code == 404


def test_trigger_embedding_not_ready_returns_409(client, trigger_service):
    trigger_service.trigger_embedding.side_effect = DocumentNotReadyForEmbeddingError("not ready")

    response = client.post("/api/v1/documents/1/embed")

    assert response.status_code == 409


def test_trigger_embedding_in_progress_returns_409(client, trigger_service):
    trigger_service.trigger_embedding.side_effect = ChunkEmbeddingAlreadyInProgressError("already running")

    response = client.post("/api/v1/documents/1/embed")

    assert response.status_code == 409


def test_trigger_embedding_unavailable_returns_503(client, trigger_service):
    trigger_service.trigger_embedding.side_effect = EmbeddingNotAvailableError("no provider")

    response = client.post("/api/v1/documents/1/embed")

    assert response.status_code == 503
