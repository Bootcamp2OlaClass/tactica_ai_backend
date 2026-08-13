"""Shared retry-classification exceptions for every Celery task.

Established in Phase 04 (`system.health_check`), reused by every real
domain task since — see PHASE_04_BACKGROUND_JOBS.md's retry-policy
convention: transient failures retry with backoff; permanent/validation
failures fail immediately and are never retried.
"""


class TransientTaskError(Exception):
    """Retryable — represents a transient failure (network blip, temporary
    external-service outage)."""


class PermanentTaskError(Exception):
    """Not retryable — represents a permanent failure (unsupported input,
    invalid domain state)."""
