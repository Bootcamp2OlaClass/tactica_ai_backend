import json
import logging

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.rag import (
    DocumentNotReadyForEmbeddingError,
    EmbeddingNotAvailableError,
)
from app.models.course import Course
from app.models.document import Document, ProcessingStatus
from app.models.semester import Semester
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.chunking import chunk_document_pages
from app.services.embedding import (
    EmbeddingNotConfiguredError,
    EmbeddingProvider,
    get_embedding_provider,
)
from app.services.storage import StorageProvider, get_storage_provider

logger = logging.getLogger(__name__)


class DocumentEmbeddingService:
    """Orchestrates one chunk+embed pass over an already Phase-05-processed
    document, reusing its exact page-labeled text artifact -- no second
    document representation, per ADR-003. A re-run replaces the document's
    chunks outright (unlike Phase 06's ExtractionCandidate, chunks carry no
    review state to preserve)."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
        document_repository: DocumentRepository | None = None,
        chunk_repository: DocumentChunkRepository | None = None,
        storage_service: StorageProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.document_repository = document_repository or DocumentRepository(db)
        self.chunk_repository = chunk_repository or DocumentChunkRepository(db)
        self.storage_service = storage_service or get_storage_provider(settings)
        self._embedding_provider = embedding_provider

    def _get_embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is not None:
            return self._embedding_provider
        try:
            return get_embedding_provider(self.settings)
        except EmbeddingNotConfiguredError as exc:
            raise EmbeddingNotAvailableError(str(exc)) from exc

    def _get_owner_user_id(self, course_id: int) -> int:
        # Same ownership chain course_repository.get_course_by_id uses
        # (Course.semester_id -> Semester.user_id) -- denormalized onto
        # every chunk at write time so retrieval never needs this join.
        return (
            self.db.query(Semester.user_id)
            .join(Course, Course.semester_id == Semester.id)
            .filter(Course.id == course_id)
            .scalar()
        )

    def embed(self, document: Document) -> list:
        """Runs one chunk+embed pass, replacing all existing chunks for
        this document. Raises DocumentNotReadyForEmbeddingError /
        EmbeddingNotAvailableError (caller classifies retry via the
        provider's own transient/permanent exceptions)."""

        if document.processing_status != ProcessingStatus.COMPLETED:
            raise DocumentNotReadyForEmbeddingError(
                "Document must finish deterministic processing "
                f"(currently {document.processing_status.value}) before "
                "it can be chunked and embedded."
            )

        if not document.extracted_content_path:
            raise DocumentNotReadyForEmbeddingError(
                "Document has no extracted text available."
            )

        provider = self._get_embedding_provider()

        artifact_bytes = self.storage_service.load(document.extracted_content_path)
        artifact = json.loads(artifact_bytes)
        pages = artifact.get("pages", [])

        drafts = chunk_document_pages(pages)

        self.chunk_repository.delete_by_document(document.id)

        if not drafts:
            self.db.commit()
            logger.info(
                "Document embedding produced no chunks (empty/whitespace-only text)",
                extra={"document_id": document.id},
            )
            return []

        embeddings = provider.embed([draft.content for draft in drafts])

        owner_user_id = self._get_owner_user_id(document.course_id)
        embedding_model_label = f"{self.settings.llm_provider}/{provider.model}"

        chunk_rows = [
            {
                "document_id": document.id,
                "course_id": document.course_id,
                "user_id": owner_user_id,
                "chunk_index": index,
                "content": draft.content,
                "start_page": draft.start_page,
                "end_page": draft.end_page,
                "embedding": embedding,
                "embedding_model": embedding_model_label,
            }
            for index, (draft, embedding) in enumerate(zip(drafts, embeddings))
        ]

        created = self.chunk_repository.bulk_create(chunk_rows)
        self.db.commit()

        logger.info(
            "Document embedding produced chunks",
            extra={"document_id": document.id, "chunk_count": len(created)},
        )

        return created
