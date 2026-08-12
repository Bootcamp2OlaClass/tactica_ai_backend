"""Internal infrastructure-proof tasks — not a product feature.

`health_check` exists solely to prove the Phase 04 plumbing works end to end
(API/process -> Redis -> Celery worker -> execution -> result) and to
demonstrate the retry-policy convention every future domain task (Phase
05+ document processing, Phase 08 AI calls, Phase 13 notifications) must
follow. It is not exposed as a real product capability.

Retry policy convention (see PHASE_04_BACKGROUND_JOBS.md):
- Transient failure (network timeout, temporary external-service/object-
  storage hiccup) -> retry, with backoff.
- Permanent failure (unsupported input, invalid domain state) -> fail
  immediately, no retry — retrying a permanent failure just wastes worker
  time and delays surfacing a real problem.
- Validation failure (malformed task arguments) -> fail immediately, no
  retry — the caller enqueued a bad request; retrying won't fix that.

Idempotency convention (see PHASE_04_BACKGROUND_JOBS.md): `task_acks_late`
is on, so a worker crash mid-task redelivers it — every future task body
must be safe to run twice with the same arguments (e.g. upsert by a natural
key / check-before-create, not a blind INSERT) rather than assuming
exactly-once execution.
"""

from celery.utils.log import get_task_logger

from app.worker.celery_app import SYSTEM_QUEUE, celery_app
from app.worker.exceptions import PermanentTaskError, TransientTaskError

logger = get_task_logger(__name__)

__all__ = ["TransientTaskError", "PermanentTaskError", "health_check"]


@celery_app.task(
    name="system.health_check",
    bind=True,
    queue=SYSTEM_QUEUE,
    max_retries=3,
    autoretry_for=(TransientTaskError,),
    retry_backoff=True,
    retry_backoff_max=30,
    retry_jitter=True,
)
def health_check(self, simulate_failure: str | None = None) -> dict:
    """Proof-of-life task. `simulate_failure` lets tests exercise the
    retry/no-retry paths without needing a real dependency to actually
    break: "transient" retries (per autoretry_for above), "permanent"
    fails immediately (PermanentTaskError isn't in autoretry_for)."""

    logger.info(
        "health_check executing",
        extra={"attempt": self.request.retries + 1},
    )

    if simulate_failure == "transient":
        raise TransientTaskError("Simulated transient failure")

    if simulate_failure == "permanent":
        raise PermanentTaskError("Simulated permanent failure")

    return {"status": "ok", "retries": self.request.retries}
