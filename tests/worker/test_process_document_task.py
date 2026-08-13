"""Unit tests for the process_document task, run in Celery's eager mode
(synchronous, in-process) against a real database and a real
LocalStorageProvider (tmp_path) -- but NOT a real separate worker process
or real Redis. See test_process_document_real_redis.py for that.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.document import ExtractionMethod, ProcessingStatus
from app.services.storage.local import LocalStorageProvider
from app.worker.celery_app import celery_app
from app.worker.tasks import documents as documents_task_module
from app.worker.tasks.documents import process_document
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
    # process_document opens its own DB session via SessionLocal (a
    # separate process/connection in real life) -- point it at the same
    # test database db_session uses, not whatever app.db.session's
    # module-level engine was configured with at first import.
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    test_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    monkeypatch.setattr(documents_task_module, "SessionLocal", test_session_local)
    yield
    engine.dispose()


@pytest.fixture
def local_storage(tmp_path, monkeypatch):
    provider = LocalStorageProvider(str(tmp_path))
    monkeypatch.setattr(
        documents_task_module, "get_storage_provider", lambda settings: provider
    )
    return provider


def _pdf_bytes(text: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    return bytes(pdf.output())


def test_successful_processing_completes_the_document(
    db_session, eager_mode, local_storage
):
    pdf_bytes = _pdf_bytes("CS 101 syllabus content, plenty of real text here.")
    storage_path = local_storage.save(pdf_bytes, "courses/1/documents/stored.pdf")

    document = create_document(db_session, storage_path=storage_path)

    result = process_document.apply(args=[document.id])

    assert result.successful()
    assert result.result["status"] == "completed"

    db_session.refresh(document)
    assert document.processing_status == ProcessingStatus.COMPLETED
    assert document.extraction_method == ExtractionMethod.NATIVE
    assert document.page_count == 1
    assert document.text_length > 0
    assert document.extracted_content_path is not None
    assert document.processing_error is None

    artifact_bytes = local_storage.load(document.extracted_content_path)
    artifact = json.loads(artifact_bytes)
    assert artifact["pages"][0]["page_number"] == 1
    assert "CS 101" in artifact["pages"][0]["text"]


def test_corrupt_pdf_marks_document_failed(db_session, eager_mode, local_storage):
    storage_path = local_storage.save(b"not a pdf", "courses/1/documents/bad.pdf")
    document = create_document(db_session, storage_path=storage_path)

    result = process_document.apply(args=[document.id])

    assert result.failed()

    db_session.refresh(document)
    assert document.processing_status == ProcessingStatus.FAILED
    assert "corrupt" in document.processing_error.lower() or "unable to read" in document.processing_error.lower()


def test_missing_storage_file_marks_document_failed(db_session, eager_mode, local_storage):
    # Never actually saved to storage -- storage_path points nowhere.
    document = create_document(
        db_session, storage_path="courses/1/documents/never-saved.pdf"
    )

    result = process_document.apply(args=[document.id])

    assert result.failed()
    db_session.refresh(document)
    assert document.processing_status == ProcessingStatus.FAILED
    assert "could not be found" in document.processing_error.lower()


def test_ocr_required_document_marks_document_failed_with_unsupported(
    db_session, eager_mode, local_storage
):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()  # blank page, no text at all
    blank_pdf_bytes = bytes(pdf.output())

    storage_path = local_storage.save(blank_pdf_bytes, "courses/1/documents/scanned.pdf")
    document = create_document(db_session, storage_path=storage_path)

    result = process_document.apply(args=[document.id])

    assert result.failed()
    db_session.refresh(document)
    assert document.processing_status == ProcessingStatus.FAILED
    assert document.extraction_method == ExtractionMethod.UNSUPPORTED
    assert "ocr" in document.processing_error.lower() or "scanned" in document.processing_error.lower()


def test_already_completed_document_is_skipped_idempotently(
    db_session, eager_mode, local_storage
):
    document = create_document(
        db_session, processing_status=ProcessingStatus.COMPLETED
    )

    result = process_document.apply(args=[document.id])

    assert result.successful()
    assert result.result["status"] == "skipped"


def test_deleted_document_is_skipped_without_error(db_session, eager_mode, local_storage):
    document = create_document(db_session)
    document.is_deleted = True
    db_session.commit()

    result = process_document.apply(args=[document.id])

    assert result.successful()
    assert result.result["status"] == "skipped"


def test_nonexistent_document_is_skipped_without_error(
    db_session, eager_mode, local_storage
):
    # db_session isn't used directly but its fixture is what creates the
    # schema this test's task-local SessionLocal queries against.
    result = process_document.apply(args=[999999])

    assert result.successful()
    assert result.result["status"] == "skipped"
