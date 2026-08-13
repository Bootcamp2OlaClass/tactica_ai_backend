class EmbeddingNotConfiguredError(Exception):
    """Raised when embedding is attempted but LLM_PROVIDER isn't set (or
    the configured provider's credential is missing). Never raised at app
    boot -- only when embedding is actually attempted."""


class EmbeddingError(Exception):
    """Raised when the provider ultimately fails to produce an embedding
    (malformed response, unexpected dimension). A permanent failure from
    the caller's perspective."""


class EmbeddingTransientError(Exception):
    """Raised for a transient provider-side failure (rate limit, timeout,
    temporary API outage) -- retryable, per the Phase 04 convention."""
