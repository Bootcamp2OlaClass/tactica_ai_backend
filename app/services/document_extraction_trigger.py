import logging

from sqlalchemy.orm import Session

from app.exceptions.document import DocumentNotFoundError
from app.exceptions.extraction import (
    DocumentNotReadyForExtractionError,
    ExtractionAlreadyInProgressError,
    ExtractionNotAvailableError,
)
from app.models.document import Document, LLMExtractionStatus, ProcessingStatus
from app.repositories import course_repository
from app.repositories.document_repository import DocumentRepository
from app.worker.tasks.extraction import extract_document

logger = logging.getLogger(__name__)

EXTRACTABLE_STATUSES = {
    LLMExtractionStatus.NOT_REQUESTED,
    LLMExtractionStatus.QUEUED,
    LLMExtractionStatus.FAILED,
}


class DocumentExtractionTriggerService:
    """Validates ownership/readiness and enqueues the Phase 06 LLM
    extraction task -- same check-then-enqueue-then-mark_queued shape as
    DocumentReprocessService. The atomic claim itself (try_start_extraction)
    happens inside the task at run time, not here."""

    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository | None = None,
    ) -> None:
        self.db = db
        self.document_repository = document_repository or DocumentRepository(db)

    def trigger_extraction(self, *, document_id: int, user_id: int) -> Document:
        document = self.document_repository.get_active_by_id(
            document_id=document_id,
        )
        if document is None:
            raise DocumentNotFoundError("Document not found.")

        course = course_repository.get_course_by_id(
            db=self.db,
            course_id=document.course_id,
            user_id=user_id,
        )
        if course is None:
            raise DocumentNotFoundError("Document not found.")

        if document.processing_status != ProcessingStatus.COMPLETED:
            raise DocumentNotReadyForExtractionError(
                "Document must finish processing "
                f"(currently {document.processing_status.value}) before "
                "AI extraction can run."
            )

        if document.llm_extraction_status not in EXTRACTABLE_STATUSES:
            raise ExtractionAlreadyInProgressError(
                "Extraction cannot be triggered while status is "
                f"{document.llm_extraction_status.value}."
            )

        try:
            extract_document.delay(document.id)

        except Exception as error:
            logger.exception(
                "Failed to enqueue document extraction",
                extra={"document_id": document.id, "user_id": user_id},
            )
            raise ExtractionNotAvailableError(
                "Unable to queue this document for AI extraction right now. "
                "Please try again shortly."
            ) from error

        return self.document_repository.mark_extraction_queued(document)
