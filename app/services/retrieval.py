"""Tenant-scoped semantic retrieval — see PHASE_07_RAG.md and ADR-003.

Phase 08 (AI Study Coach) is the first real consumer. This module
deliberately stays retrieval-only: it returns ranked chunks with
provenance, never calls a generation model itself (see PHASE_07_RAG.md's
scope boundary against becoming the Study Coach prematurely).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.rag import EmbeddingNotAvailableError
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.services.embedding import (
    EmbeddingNotConfiguredError,
    EmbeddingProvider,
    get_embedding_provider,
)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    course_id: int
    content: str
    start_page: int
    end_page: int


class RetrievalService:
    """`user_id` is mandatory, never optional, and enforced at the SQL
    level via DocumentChunkRepository.search -- see
    tests/services/test_retrieval.py for the cross-user isolation proof
    every code path here must satisfy, including semantic-search cases
    where two users' chunks have identical or near-identical embeddings."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
        chunk_repository: DocumentChunkRepository | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.chunk_repository = chunk_repository or DocumentChunkRepository(db)
        self._embedding_provider = embedding_provider

    def _get_embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is not None:
            return self._embedding_provider
        try:
            return get_embedding_provider(self.settings)
        except EmbeddingNotConfiguredError as exc:
            raise EmbeddingNotAvailableError(str(exc)) from exc

    def search(
        self,
        *,
        user_id: int,
        query: str,
        course_id: int | None = None,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        provider = self._get_embedding_provider()
        query_embedding = provider.embed([query])[0]

        chunks = self.chunk_repository.search(
            user_id=user_id,
            query_embedding=query_embedding,
            course_id=course_id,
            top_k=top_k,
        )

        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                course_id=chunk.course_id,
                content=chunk.content,
                start_page=chunk.start_page,
                end_page=chunk.end_page,
            )
            for chunk in chunks
        ]
