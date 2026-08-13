"""Centralized Celery application — see ADR-005.

The worker is a separate process from the FastAPI app (`celery -A
app.worker.celery_app worker`, not something started inside `uvicorn`).
Importing this module has no side effect requiring Redis to be reachable —
Celery's client/connection is lazy, so both the API process (which only
*publishes* tasks) and a broken/absent worker don't block FastAPI startup.
See PHASE_04_BACKGROUND_JOBS.md for the health-check-doesn't-block-boot
rationale.
"""

from celery import Celery
from celery.signals import before_task_publish, task_postrun, task_prerun

from app.core.config import get_settings
from app.core.logging import (
    TASK_ID_MISSING,
    REQUEST_ID_MISSING,
    configure_logging,
    get_request_id,
    reset_request_id,
    reset_task_id,
    set_request_id,
    set_task_id,
)

settings = get_settings()

# Reuse the same structured/redacted logging setup the API process uses,
# instead of Celery's own default logging config.
configure_logging()


# Domain queue *names* only — Phase 04 doesn't populate them with real
# tasks (see ADR-005 / PHASE_04 notes: "build only the foundation needed").
# Phase 05+ should route real tasks to these instead of inventing new names.
DOCUMENTS_QUEUE = "documents"
AI_QUEUE = "ai"
NOTIFICATIONS_QUEUE = "notifications"
CALENDAR_QUEUE = "calendar"
SYSTEM_QUEUE = "system"  # infra-only tasks (e.g. the Phase 04 health check)

celery_app = Celery(
    "tactica_ai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.worker.tasks.system",
        "app.worker.tasks.documents",
        "app.worker.tasks.extraction",
        "app.worker.tasks.rag",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],  # never accept pickle — arbitrary code execution risk
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    worker_hijack_root_logger=False,
    task_default_queue=SYSTEM_QUEUE,
)


# --- Request/job correlation (see PHASE_04_BACKGROUND_JOBS.md) -------------
#
# Whatever HTTP request is in flight when a task is enqueued has its
# request_id attached to the task's headers automatically; the worker then
# makes that same request_id (plus the task's own id) available to every log
# line emitted while the task runs, via the same ContextVar-based mechanism
# app/core/logging.py already uses for HTTP requests.

_context_tokens: dict[str, tuple] = {}


@before_task_publish.connect
def _attach_request_id_header(headers=None, **_kwargs) -> None:
    if headers is None:
        return
    headers.setdefault("request_id", get_request_id())


@task_prerun.connect
def _set_task_logging_context(task_id=None, task=None, **_kwargs) -> None:
    request_id = REQUEST_ID_MISSING
    if task is not None:
        request_id = task.request.get("request_id") or REQUEST_ID_MISSING

    request_token = set_request_id(request_id)
    task_token = set_task_id(task_id or TASK_ID_MISSING)
    _context_tokens[task_id] = (request_token, task_token)


@task_postrun.connect
def _reset_task_logging_context(task_id=None, **_kwargs) -> None:
    tokens = _context_tokens.pop(task_id, None)
    if tokens is None:
        return
    request_token, task_token = tokens
    reset_request_id(request_token)
    reset_task_id(task_token)


# `include=` above is what `celery -A app.worker.celery_app worker` uses to
# autodiscover task modules, but it's lazy — anything importing celery_app
# directly (the API process calling .delay(), tests) needs the task modules
# actually imported to register decorated tasks. Import explicitly here too.
import app.worker.tasks.system  # noqa: E402,F401
import app.worker.tasks.documents  # noqa: E402,F401
import app.worker.tasks.extraction  # noqa: E402,F401
import app.worker.tasks.rag  # noqa: E402,F401
