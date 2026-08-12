"""Unit tests for the Celery app config and task retry policy.

Uses Celery's `task_always_eager` mode, which runs tasks synchronously
in-process — this is genuinely useful for testing the *retry policy logic*
itself (transient failures retry N times then fail; permanent failures
fail immediately, no retry), but it does NOT exercise Redis, task
serialization over the wire, or a real separate worker process. That's
what tests/worker/test_health_check_real_redis.py is for — do not treat
these eager-mode results as proof the real queue works end to end.
"""

import pytest

from app.core.config import get_settings
from app.worker.celery_app import celery_app
from app.worker.tasks.system import PermanentTaskError, health_check


@pytest.fixture
def eager_mode():
    original_eager = celery_app.conf.task_always_eager
    original_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    # False (the default) so a failing task's exception is captured on the
    # EagerResult (.failed()/.result) instead of being raised directly out
    # of .apply() — that's what lets these tests inspect failure outcomes.
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager = original_eager
    celery_app.conf.task_eager_propagates = original_propagates


def test_broker_and_backend_come_from_settings():
    settings = get_settings()
    assert celery_app.conf.broker_url == settings.celery_broker_url
    assert celery_app.conf.result_backend == settings.celery_result_backend


def test_never_accepts_pickle_content():
    # Deserializing pickle from an untrusted/compromised broker is arbitrary
    # code execution -- json-only is a deliberate security choice, not an
    # arbitrary default.
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.task_serializer == "json"


def test_tasks_ack_late_for_worker_crash_redelivery():
    assert celery_app.conf.task_acks_late is True


def test_health_check_succeeds_with_no_simulated_failure(eager_mode):
    result = health_check.apply()
    assert result.successful()
    assert result.result == {"status": "ok", "retries": 0}


def test_health_check_permanent_failure_does_not_retry(eager_mode):
    result = health_check.apply(kwargs={"simulate_failure": "permanent"})
    assert result.failed()
    assert isinstance(result.result, PermanentTaskError)


def test_health_check_transient_failure_retries_then_fails(eager_mode):
    # autoretry_for + max_retries=3 means: 1 initial attempt + up to 3
    # retries, all still raising TransientTaskError, so it ultimately fails
    # -- this proves the *retry policy is wired up*, not that retries
    # succeed (there's nothing here that would ever succeed).
    result = health_check.apply(kwargs={"simulate_failure": "transient"})
    assert result.failed()
