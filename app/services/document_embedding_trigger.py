import logging

from sqlalchemy.orm import Session

from app.exceptions.document import DocumentNotFoundError
from app.exceptions.rag import (
    ChunkEmbeddingAlreadyInProgressError,
    DocumentNotReadyForEmbeddingError,
    EmbeddingNotAvailableError,
)
from app.models.document import ChunkEmbeddingStatus, Document, ProcessingStatus
from app.repositories import course_repository
from app.repositories.document_repository import DocumentRepository
from app.worker.tasks.rag import embed_document

logger = logging.getLogger(__name__)

EMBEDDABLE_STATUSES = {
    ChunkEmbeddingStatus.NOT_REQUESTED,
    ChunkEmbeddingStatus.QUEUED,
    ChunkEmbeddingStatus.FAILED,
}


class DocumentEmbeddingTriggerService:
    """Validates ownership/readiness and enqueues the Phase 07 chunk+embed
    task -- same check-then-enqueue-then-mark_queued shape as
    DocumentExtractionTriggerService (Phase 06) / DocumentReprocessService
    (Phase 05). The atomic claim (try_start_chunk_embedding) happens inside
    the task at run time, not here."""

    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository | None = None,
    ) -> None:
        self.db = db
        self.document_repository = document_repository or DocumentRepository(db)

    def trigger_embedding(self, *, document_id: int, user_id: int) -> Document:
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
            raise DocumentNotReadyForEmbeddingError(
                "Document must finish processing "
                f"(currently {document.processing_status.value}) before "
                "it can be chunked and embedded."
            )

        if document.chunk_embedding_status not in EMBEDDABLE_STATUSES:
            raise ChunkEmbeddingAlreadyInProgressError(
                "Chunking/embedding cannot be triggered while status is "
                f"{document.chunk_embedding_status.value}."
            )

        try:
            embed_document.delay(document.id)

        except Exception as error:
            logger.exception(
                "Failed to enqueue document embedding",
                extra={"document_id": document.id, "user_id": user_id},
            )
            raise EmbeddingNotAvailableError(
                "Unable to queue this document for AI embedding right now. "
                "Please try again shortly."
            ) from error

        return self.document_repository.mark_chunk_embedding_queued(document)
