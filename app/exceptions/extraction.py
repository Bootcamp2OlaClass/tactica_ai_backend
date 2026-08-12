class ExtractionError(Exception):
    """Base exception for structured-extraction operations."""


class DocumentNotReadyForExtractionError(ExtractionError):
    """Raised when extraction is requested but the document hasn't
    finished Phase 05's deterministic processing yet (or failed it)."""


class ExtractionNotAvailableError(ExtractionError):
    """Raised when no LLM provider is configured, or the provider is
    temporarily unreachable at request time."""


class ExtractionCandidateNotFoundError(ExtractionError):
    """Raised when a candidate doesn't exist or isn't owned by the
    requesting user."""


class ExtractionCandidateAlreadyReviewedError(ExtractionError):
    """Raised when accept/reject is attempted on a candidate that's
    already been accepted or rejected."""


class ExtractionAlreadyInProgressError(ExtractionError):
    """Raised when /extract is triggered while the document's current
    llm_extraction_status doesn't allow (re-)triggering (already QUEUED/
    PROCESSING, or COMPLETED -- re-running a finished extraction isn't
    this endpoint's job, same boundary as document reprocessing)."""
