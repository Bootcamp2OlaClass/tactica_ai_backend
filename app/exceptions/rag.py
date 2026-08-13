class RagError(Exception):
    """Base exception for chunk/embed/retrieval operations."""


class DocumentNotReadyForEmbeddingError(RagError):
    """Raised when embedding is requested but the document hasn't finished
    Phase 05's deterministic processing yet (or failed it)."""


class EmbeddingNotAvailableError(RagError):
    """Raised when no embedding provider is configured, or the provider is
    temporarily unreachable at request time."""


class ChunkEmbeddingAlreadyInProgressError(RagError):
    """Raised when /embed is triggered while the document's current
    chunk_embedding_status doesn't allow (re-)triggering."""
