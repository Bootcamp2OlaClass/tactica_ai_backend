"""Chunk+embed task — see PHASE_07_RAG.md.

Mirrors app/worker/tasks/extraction.py's idempotency design exactly (which
itself mirrors app/worker/tasks/documents.py): an atomic UPDATE...WHERE
claim (DocumentRepository.try_start_chunk_embedding), retries skip the
claim (self.request.retries == 0 gate), and a custom Task.on_failure marks
the document FAILED exactly once if retries are ultimately exhausted.
"""

from celery import Task
from celery.utils.log import get_task_logger

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.exceptions.rag import (
    DocumentNotReadyForEmbeddingError,
    EmbeddingNotAvailableError,
)
from app.models.document import ChunkEmbeddingStatus
from app.repositories.document_repository import DocumentRepository
from app.services.document_embedding import DocumentEmbeddingService
from app.services.embedding import EmbeddingError, EmbeddingTransientError
from app.worker.celery_app import AI_QUEUE, celery_app
from app.worker.exceptions import PermanentTaskError, TransientTaskError

logger = get_task_logger(__name__)
settings = get_settings()


class ChunkEmbeddingTask(Task):
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
                and document.chunk_embedding_status == ChunkEmbeddingStatus.PROCESSING
            ):
                repository.mark_chunk_embedding_failed(
                    document, "Chunking/embedding failed after repeated attempts."
                )
        finally:
            db.close()


@celery_app.task(
    name="ai.embed_document",
    bind=True,
    base=ChunkEmbeddingTask,
    queue=AI_QUEUE,
    max_retries=3,
    autoretry_for=(TransientTaskError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def embed_document(self, document_id: int) -> dict:
    db = SessionLocal()
    try:
        repository = DocumentRepository(db)

        if self.request.retries == 0:
            claimed = repository.try_start_chunk_embedding(document_id)
            if not claimed:
                document = repository.get_by_id(document_id)
                if document is None:
                    logger.info(
                        "embed_document: document not found or deleted, skipping",
                        extra={"document_id": document_id},
                    )
                    return {"status": "skipped", "reason": "not_found"}
                logger.info(
                    "embed_document: not claimable, skipping",
                    extra={
                        "document_id": document_id,
                        "chunk_embedding_status": document.chunk_embedding_status.value,
                    },
                )
                return {
                    "status": "skipped",
                    "reason": f"status_{document.chunk_embedding_status.value.lower()}",
                }

        document = repository.get_by_id(document_id)
        if document is None:
            logger.info(
                "embed_document: document deleted mid-flight, skipping",
                extra={"document_id": document_id},
            )
            return {"status": "skipped", "reason": "deleted_mid_flight"}

        logger.info(
            "embed_document: started",
            extra={"document_id": document_id, "attempt": self.request.retries + 1},
        )

        service = DocumentEmbeddingService(db=db, settings=settings)

        try:
            chunks = service.embed(document)
        except DocumentNotReadyForEmbeddingError as exc:
            repository.mark_chunk_embedding_failed(document, str(exc))
            raise PermanentTaskError(str(exc)) from exc
        except EmbeddingNotAvailableError as exc:
            repository.mark_chunk_embedding_failed(
                document, "AI embedding is not currently available."
            )
            raise PermanentTaskError(str(exc)) from exc
        except EmbeddingError as exc:
            repository.mark_chunk_embedding_failed(
                document,
                "Embedding did not produce usable output for this document.",
            )
            raise PermanentTaskError(str(exc)) from exc
        except EmbeddingTransientError as exc:
            raise TransientTaskError(str(exc)) from exc

        repository.mark_chunk_embedding_completed(document)

        logger.info(
            "embed_document: completed",
            extra={"document_id": document_id, "chunk_count": len(chunks)},
        )

        return {
            "status": "completed",
            "document_id": document_id,
            "chunk_count": len(chunks),
        }
    finally:
        db.close()
