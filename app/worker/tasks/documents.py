"""The real document-processing pipeline task — see
PHASE_05_DOCUMENT_PROCESSING.md for the full design writeup.

process_document(document_id) drives a Document through:
  PROCESSING -> read via StorageProvider -> validate -> extract native text
  -> OCR-required check -> normalize -> persist -> COMPLETED / FAILED

Idempotency: a single UPDATE...WHERE claims the document atomically
(DocumentRepository.try_start_processing) so two concurrent enqueues of
the same document_id can't both process it. A *retry* of the same task
(same Celery task_id, `self.request.retries > 0`) is not a duplicate —
it's a continuation of the attempt that already claimed the document — so
retries skip the claim and proceed directly. See "Idempotency /
Concurrency" in the phase doc for the full reasoning, including why this
would NOT be safe if the claim were skipped for genuinely new task_ids.

Retry policy: storage read/write failures are TransientTaskError (retried
with backoff, per the Phase 04 convention). A corrupt/unparseable PDF, a
missing stored file, or an OCR-required-but-unsupported document are all
permanent, domain-level failures — the document is marked FAILED with a
safe, specific error message and the task raises PermanentTaskError (never
retried). If a TransientTaskError exhausts all its retries,
DocumentProcessingTask.on_failure marks the document FAILED with a generic
message exactly once, so a document can never stay stuck in PROCESSING
forever.
"""

import json
from typing import NoReturn

from celery import Task
from celery.utils.log import get_task_logger

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.document import ExtractionMethod, ProcessingStatus
from app.repositories.document_repository import DocumentRepository
from app.services.document_processing import (
    PdfCorruptError,
    extract_native_pdf_text,
    normalize_text,
    requires_ocr,
)
from app.services.storage import get_storage_provider
from app.worker.celery_app import DOCUMENTS_QUEUE, celery_app
from app.worker.exceptions import PermanentTaskError, TransientTaskError

logger = get_task_logger(__name__)
settings = get_settings()


class DocumentProcessingTask(Task):
    """Celery calls `on_failure` exactly once, after retries are exhausted
    (or immediately for a non-retried exception) — the one place that can
    reliably guarantee a document never stays stuck in PROCESSING if a
    transient error exhausts all its retries."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        document_id = args[0] if args else kwargs.get("document_id")
        if document_id is None:
            return

        db = SessionLocal()
        try:
            repository = DocumentRepository(db)
            document = repository.get_by_id(document_id)

            if document is not None and document.processing_status == ProcessingStatus.PROCESSING:
                repository.mark_failed(
                    document,
                    "Document processing failed after repeated attempts.",
                )
        finally:
            db.close()


def _fail(
    repository: DocumentRepository,
    document,
    message: str,
    *,
    extraction_method: ExtractionMethod | None = None,
) -> NoReturn:
    repository.mark_failed(document, message, extraction_method=extraction_method)
    raise PermanentTaskError(message)


@celery_app.task(
    name="documents.process_document",
    bind=True,
    base=DocumentProcessingTask,
    queue=DOCUMENTS_QUEUE,
    max_retries=3,
    autoretry_for=(TransientTaskError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def process_document(self, document_id: int) -> dict:
    db = SessionLocal()
    try:
        repository = DocumentRepository(db)

        # Only the *first* attempt claims the document (see module
        # docstring) — a retry of this same task continues the attempt
        # that already claimed it.
        if self.request.retries == 0:
            claimed = repository.try_start_processing(document_id)
            if not claimed:
                document = repository.get_by_id(document_id)
                if document is None:
                    logger.info(
                        "process_document: document not found or deleted, skipping",
                        extra={"document_id": document_id},
                    )
                    return {"status": "skipped", "reason": "not_found"}

                logger.info(
                    "process_document: document not claimable, skipping",
                    extra={
                        "document_id": document_id,
                        "processing_status": document.processing_status.value,
                    },
                )
                return {
                    "status": "skipped",
                    "reason": f"status_{document.processing_status.value.lower()}",
                }

        document = repository.get_by_id(document_id)
        if document is None:
            # Deleted between claiming and this fetch -- nothing to do.
            logger.info(
                "process_document: document deleted mid-flight, skipping",
                extra={"document_id": document_id},
            )
            return {"status": "skipped", "reason": "deleted_mid_flight"}

        logger.info(
            "process_document: processing started",
            extra={
                "document_id": document_id,
                "course_id": document.course_id,
                "attempt": self.request.retries + 1,
            },
        )

        storage = get_storage_provider(settings)

        try:
            file_content = storage.load(document.storage_path)
        except FileNotFoundError:
            _fail(repository, document, "The stored file could not be found.")
        except (OSError, ValueError) as exc:
            raise TransientTaskError(f"Storage read failed: {exc}") from exc

        try:
            pages = extract_native_pdf_text(file_content)
        except PdfCorruptError:
            _fail(
                repository,
                document,
                "Unable to read this PDF — it may be corrupted or invalid.",
            )

        if requires_ocr(pages):
            _fail(
                repository,
                document,
                "This document appears to be a scanned or image-based PDF. "
                "OCR processing is not yet available for this file.",
                extraction_method=ExtractionMethod.UNSUPPORTED,
            )

        normalized_pages = [normalize_text(page.text) for page in pages]

        artifact_key = (
            f"courses/{document.course_id}/documents/"
            f"{document.stored_file_name}.extracted.json"
        )
        artifact_payload = json.dumps(
            {
                "document_id": document.id,
                "pages": [
                    {
                        "page_number": index,
                        "text": text,
                        "extraction_method": ExtractionMethod.NATIVE.value,
                    }
                    for index, text in enumerate(normalized_pages, start=1)
                ],
            }
        ).encode("utf-8")

        try:
            extracted_content_path = storage.save(artifact_payload, artifact_key)
        except (OSError, ValueError) as exc:
            raise TransientTaskError(f"Storage write failed: {exc}") from exc

        text_length = sum(len(text) for text in normalized_pages)

        repository.mark_completed(
            document,
            extraction_method=ExtractionMethod.NATIVE,
            page_count=len(normalized_pages),
            text_length=text_length,
            extracted_content_path=extracted_content_path,
        )

        logger.info(
            "process_document: completed",
            extra={
                "document_id": document_id,
                "page_count": len(normalized_pages),
                "text_length": text_length,
            },
        )

        return {
            "status": "completed",
            "document_id": document_id,
            "page_count": len(normalized_pages),
        }
    finally:
        db.close()
