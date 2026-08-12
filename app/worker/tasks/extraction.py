"""LLM structured-extraction task — see PHASE_06_STRUCTURED_EXTRACTION.md.

Mirrors app/worker/tasks/documents.py's idempotency design exactly: an
atomic UPDATE...WHERE claim (DocumentRepository.try_start_extraction),
retries skip the claim (self.request.retries == 0 gate) rather than
re-attempting it, and a custom Task.on_failure marks the document FAILED
exactly once if retries are ultimately exhausted. See that module's
docstring for the full reasoning -- not repeated here.

Never writes to Task/Course directly (see app/services/extraction_review.py
for the accept-gated write path) -- this task only ever produces
ExtractionCandidate rows, per ADR-006.
"""

from celery import Task
from celery.utils.log import get_task_logger

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.exceptions.extraction import (
    DocumentNotReadyForExtractionError,
    ExtractionNotAvailableError,
)
from app.models.document import LLMExtractionStatus
from app.repositories.document_repository import DocumentRepository
from app.services.document_extraction import DocumentExtractionService
from app.services.llm import LLMExtractionError, LLMTransientError
from app.worker.celery_app import AI_QUEUE, celery_app
from app.worker.exceptions import PermanentTaskError, TransientTaskError

logger = get_task_logger(__name__)
settings = get_settings()


class ExtractionTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        document_id = args[0] if args else kwargs.get("document_id")
        if document_id is None:
            return

        db = SessionLocal()
        try:
            repository = DocumentRepository(db)
            document = repository.get_by_id(document_id)
            if (
                document is not None
                and document.llm_extraction_status == LLMExtractionStatus.PROCESSING
            ):
                repository.mark_extraction_failed(
                    document, "Extraction failed after repeated attempts."
                )
        finally:
            db.close()


@celery_app.task(
    name="ai.extract_document",
    bind=True,
    base=ExtractionTask,
    queue=AI_QUEUE,
    max_retries=3,
    autoretry_for=(TransientTaskError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def extract_document(self, document_id: int) -> dict:
    db = SessionLocal()
    try:
        repository = DocumentRepository(db)

        if self.request.retries == 0:
            claimed = repository.try_start_extraction(document_id)
            if not claimed:
                document = repository.get_by_id(document_id)
                if document is None:
                    logger.info(
                        "extract_document: document not found or deleted, skipping",
                        extra={"document_id": document_id},
                    )
                    return {"status": "skipped", "reason": "not_found"}
                logger.info(
                    "extract_document: not claimable, skipping",
                    extra={
                        "document_id": document_id,
                        "llm_extraction_status": document.llm_extraction_status.value,
                    },
                )
                return {
                    "status": "skipped",
                    "reason": f"status_{document.llm_extraction_status.value.lower()}",
                }

        document = repository.get_by_id(document_id)
        if document is None:
            logger.info(
                "extract_document: document deleted mid-flight, skipping",
                extra={"document_id": document_id},
            )
            return {"status": "skipped", "reason": "deleted_mid_flight"}

        logger.info(
            "extract_document: started",
            extra={"document_id": document_id, "attempt": self.request.retries + 1},
        )

        service = DocumentExtractionService(db=db, settings=settings)

        try:
            candidates = service.extract(document)
        except DocumentNotReadyForExtractionError as exc:
            repository.mark_extraction_failed(document, str(exc))
            raise PermanentTaskError(str(exc)) from exc
        except ExtractionNotAvailableError as exc:
            repository.mark_extraction_failed(
                document, "AI extraction is not currently available."
            )
            raise PermanentTaskError(str(exc)) from exc
        except LLMExtractionError as exc:
            repository.mark_extraction_failed(
                document,
                "The AI extraction did not produce usable output for this document.",
            )
            raise PermanentTaskError(str(exc)) from exc
        except LLMTransientError as exc:
            raise TransientTaskError(str(exc)) from exc

        repository.mark_extraction_completed(document)

        logger.info(
            "extract_document: completed",
            extra={"document_id": document_id, "candidate_count": len(candidates)},
        )

        return {
            "status": "completed",
            "document_id": document_id,
            "candidate_count": len(candidates),
        }
    finally:
        db.close()
