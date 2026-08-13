class LLMNotConfiguredError(Exception):
    """Raised when extraction is attempted but LLM_PROVIDER isn't set (or
    the configured provider's credential is missing). Never raised at app
    boot -- only when extraction is actually attempted, matching the
    optional-infrastructure pattern used for Redis/R2."""


class LLMExtractionError(Exception):
    """Raised when the provider ultimately fails to produce schema-valid
    structured output (after the provider SDK's own retry/repair, if any).
    A permanent failure from the caller's perspective -- retrying the same
    document/prompt without changes is unlikely to succeed."""


class LLMTransientError(Exception):
    """Raised for a transient provider-side failure (rate limit, timeout,
    temporary API outage) -- retryable, per the Phase 04 convention."""
