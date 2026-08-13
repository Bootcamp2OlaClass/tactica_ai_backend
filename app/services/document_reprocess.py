import logging

from sqlalchemy.orm import Session

from app.exceptions.document import (
    DocumentNotFoundError,
    DocumentProcessingUnavailableError,
    DocumentReprocessNotAllowedError,
)
from app.exceptions.course import CourseNotFoundError
from app.models.document import Document, ProcessingStatus
from app.repositories import course_repository
from app.repositories.document_repository import DocumentRepository
from app.worker.tasks.documents import process_document

logger = logging.getLogger(__name__)

REPROCESSABLE_STATUSES = {ProcessingStatus.UPLOADED, ProcessingStatus.FAILED}


class DocumentReprocessService:
    """Gives a document stuck in UPLOADED (enqueue failed at upload time)
    or FAILED (permanent processing failure) an explicit retry path — see
    PHASE_05_DOCUMENT_PROCESSING.md "Failure Consistency"."""

    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository | None = None,
    ) -> None:
        self.db = db
        self.document_repository = (
            document_repository
            if document_repository is not None
            else DocumentRepository(db)
        )

    def reprocess_document(
        self,
        *,
        document_id: int,
        user_id: int,
    ) -> Document:
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

        if document.processing_status not in REPROCESSABLE_STATUSES:
            raise DocumentReprocessNotAllowedError(
                "Document cannot be reprocessed while its status is "
                f"{document.processing_status.value}."
            )

        try:
            process_document.delay(document.id)

        except Exception as error:
            logger.exception(
                "Failed to enqueue document reprocessing",
                extra={"document_id": document.id, "user_id": user_id},
            )
            raise DocumentProcessingUnavailableError(
                "Unable to queue this document for reprocessing right now. "
                "Please try again shortly."
            ) from error

        return self.document_repository.mark_queued(document)
