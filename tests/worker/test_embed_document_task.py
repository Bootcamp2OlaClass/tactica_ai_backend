"""Unit tests for the embed_document task, run in Celery's eager mode
(synchronous, in-process) against a real database and a real
LocalStorageProvider (tmp_path), with a fake embedding provider standing in
for Gemini/OpenAI -- mirrors test_extract_document_task.py's pattern.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.document import ChunkEmbeddingStatus, ProcessingStatus
from app.services.embedding import EmbeddingError, EmbeddingTransientError
from app.services.storage.local import LocalStorageProvider
from app.worker.celery_app import celery_app
from app.worker.tasks import rag as rag_task_module
from app.worker.tasks.rag import embed_document
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
    monkeypatch.setattr(rag_task_module, "SessionLocal", test_session_local)
    yield
    engine.dispose()


class FakeEmbeddingProvider:
    model = "fake-embedding-model"

    def __init__(self, vector=None, exc=None):
        self._vector = vector or [0.1] * 768
        self.exc = exc

    def embed(self, texts):
        if self.exc is not None:
            raise self.exc
        return [self._vector for _ in texts]


@pytest.fixture
def local_storage_with_extracted_document(tmp_path, monkeypatch, db_session):
    provider = LocalStorageProvider(str(tmp_path))
    artifact_key = "courses/1/documents/stored.pdf.extracted.json"
    provider.save(
        json.dumps(
            {"pages": [{"page_number": 1, "text": "CS101 syllabus text for embedding."}]}
        ).encode("utf-8"),
        artifact_key,
    )

    document = create_document(db_session, processing_status=ProcessingStatus.COMPLETED)
    document.extracted_content_path = artifact_key
    db_session.commit()
    db_session.refresh(document)

    monkeypatch.setattr(
        "app.services.document_embedding.get_storage_provider", lambda settings: provider
    )

    return document


def _patch_provider(monkeypatch, provider):
    monkeypatch.setattr(
        "app.services.document_embedding.get_embedding_provider", lambda settings: provider
    )


def test_successful_embedding_creates_chunks_and_completes(
    db_session, eager_mode, local_storage_with_extracted_document, monkeypatch
):
    document = local_storage_with_extracted_document
    _patch_provider(monkeypatch, FakeEmbeddingProvider())

    result = embed_document.apply(args=[document.id])

    assert result.successful()
    assert result.result["status"] == "completed"
    assert result.result["chunk_count"] == 1

    db_session.refresh(document)
    assert document.chunk_embedding_status == ChunkEmbeddingStatus.COMPLETED
    assert document.chunk_embedding_error is None

    chunks = document.chunks
    assert len(chunks) == 1
    assert chunks[0].embedding is not None
    assert chunks[0].start_page == 1


def test_document_not_ready_marks_failed_permanently(db_session, eager_mode, tmp_path, monkeypatch):
    provider = LocalStorageProvider(str(tmp_path))
    monkeypatch.setattr(
        "app.services.document_embedding.get_storage_provider", lambda settings: provider
    )
    document = create_document(db_session, processing_status=ProcessingStatus.UPLOADED)

    result = embed_document.apply(args=[document.id])

    assert result.failed()
    db_session.refresh(document)
    assert document.chunk_embedding_status == ChunkEmbeddingStatus.FAILED
    assert document.chunk_embedding_error is not None


def test_embedding_error_marks_failed_permanently(
    db_session, eager_mode, local_storage_with_extracted_document, monkeypatch
):
    document = local_storage_with_extracted_document
    _patch_provider(monkeypatch, FakeEmbeddingProvider(exc=EmbeddingError("bad output")))

    result = embed_document.apply(args=[document.id])

    assert result.failed()
    db_session.refresh(document)
    assert document.chunk_embedding_status == ChunkEmbeddingStatus.FAILED
    assert "did not produce usable output" in document.chunk_embedding_error


def test_transient_error_retries_then_fails_via_on_failure(
    db_session, eager_mode, local_storage_with_extracted_document, monkeypatch
):
    document = local_storage_with_extracted_document
    _patch_provider(monkeypatch, FakeEmbeddingProvider(exc=EmbeddingTransientError("timeout")))

    result = embed_document.apply(args=[document.id])

    assert result.failed()
    db_session.refresh(document)
    assert document.chunk_embedding_status == ChunkEmbeddingStatus.FAILED
    assert "repeated attempts" in document.chunk_embedding_error


def test_already_completed_document_is_skipped_idempotently(db_session, eager_mode, tmp_path, monkeypatch):
    provider = LocalStorageProvider(str(tmp_path))
    monkeypatch.setattr(
        "app.services.document_embedding.get_storage_provider", lambda settings: provider
    )
    document = create_document(db_session, processing_status=ProcessingStatus.COMPLETED)
    document.chunk_embedding_status = ChunkEmbeddingStatus.COMPLETED
    db_session.commit()

    result = embed_document.apply(args=[document.id])

    assert result.successful()
    assert result.result["status"] == "skipped"


def test_deleted_document_is_skipped_without_error(db_session, eager_mode, tmp_path, monkeypatch):
    provider = LocalStorageProvider(str(tmp_path))
    monkeypatch.setattr(
        "app.services.document_embedding.get_storage_provider", lambda settings: provider
    )
    document = create_document(db_session)
    document.is_deleted = True
    db_session.commit()

    result = embed_document.apply(args=[document.id])

    assert result.successful()
    assert result.result["status"] == "skipped"


def test_nonexistent_document_is_skipped_without_error(db_session, eager_mode, tmp_path, monkeypatch):
    provider = LocalStorageProvider(str(tmp_path))
    monkeypatch.setattr(
        "app.services.document_embedding.get_storage_provider", lambda settings: provider
    )
    result = embed_document.apply(args=[999999])

    assert result.successful()
    assert result.result["status"] == "skipped"


def test_rerun_replaces_existing_chunks(
    db_session, eager_mode, local_storage_with_extracted_document, monkeypatch
):
    document = local_storage_with_extracted_document
    _patch_provider(monkeypatch, FakeEmbeddingProvider(vector=[0.1] * 768))
    first_result = embed_document.apply(args=[document.id])
    assert first_result.successful()

    db_session.refresh(document)
    document.chunk_embedding_status = ChunkEmbeddingStatus.QUEUED
    db_session.commit()

    _patch_provider(monkeypatch, FakeEmbeddingProvider(vector=[0.9] * 768))
    second_result = embed_document.apply(args=[document.id])
    assert second_result.successful()

    db_session.refresh(document)
    chunks = document.chunks
    assert len(chunks) == 1
    assert chunks[0].embedding[0] == pytest.approx(0.9, abs=0.01)
