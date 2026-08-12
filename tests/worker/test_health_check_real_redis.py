"""Real integration test: API/test process -> Redis -> a genuine separate
Celery worker process -> execution -> result.

Unlike test_celery_config.py's eager-mode tests, this spawns an actual
`celery worker` subprocess and talks to it purely through Redis, the same
way the real API process and the real worker process would in dev/prod.
Automatically skipped (not failed) if the dedicated test Redis instance
below isn't reachable, so the rest of the suite/CI is unaffected when no
Redis is running -- but when it IS available, this proves the queue
actually works end to end, not just that the retry-policy logic is wired
up correctly in isolation.

Deliberately points at redis://localhost:6380/1 rather than whatever
REDIS_URL happens to be set to -- this machine may have an unrelated
Redis already running on the default port 6379 for a different project,
and this test must never touch that.
"""

import subprocess
import sys
import threading
import time

import pytest

from app.worker.celery_app import celery_app

TEST_REDIS_URL = "redis://localhost:6380/1"


def _redis_reachable(url: str) -> bool:
    import redis

    try:
        return bool(redis.from_url(url, socket_connect_timeout=1).ping())
    except Exception:
        return False


@pytest.fixture(scope="module")
def redis_available():
    if not _redis_reachable(TEST_REDIS_URL):
        pytest.skip(
            f"No Redis reachable at {TEST_REDIS_URL} -- start a disposable "
            "instance there to run this real integration test "
            "(e.g. `docker run -p 6380:6379 redis:7-alpine`)."
        )
    return True


@pytest.fixture(scope="module", autouse=True)
def _point_celery_client_at_test_redis(redis_available):
    # The test process's own `celery_app` (used for .delay()/AsyncResult)
    # may already have been constructed -- and had its connection pool and
    # result backend lazily instantiated and cached -- against whatever
    # REDIS_URL was active earlier in this test session (e.g. another test
    # module import order), not necessarily this test's dedicated instance.
    # Changing `conf.broker_url`/`conf.result_backend` alone does NOT
    # invalidate `_pool`/`_backend`, which Celery caches once created; left
    # alone, .get() would silently keep listening on the wrong Redis and
    # time out even though the real worker (correctly pointed at the test
    # Redis via its own subprocess env) actually completed the task. Reset
    # both caches so they're rebuilt against the new config on next use.
    original_broker = celery_app.conf.broker_url
    original_backend = celery_app.conf.result_backend
    celery_app.conf.broker_url = TEST_REDIS_URL
    celery_app.conf.result_backend = TEST_REDIS_URL
    celery_app._pool = None
    celery_app._backend_cache = None
    celery_app._local.__dict__.pop("backend", None)
    # `amqp` is a cached_property (stored directly in __dict__) holding the
    # publish-side Producer/connection machinery -- must be reset too, or
    # a later real-Redis test module's .delay() can silently publish
    # through a Producer still bound to *this* module's broker. See
    # test_process_document_real_redis.py for the full account (found
    # there, applied back here for the same latent risk).
    celery_app.__dict__.pop("amqp", None)
    yield
    celery_app.conf.broker_url = original_broker
    celery_app.conf.result_backend = original_backend
    celery_app._pool = None
    celery_app._backend_cache = None
    celery_app._local.__dict__.pop("backend", None)
    celery_app.__dict__.pop("amqp", None)


@pytest.fixture(scope="module")
def worker_process(redis_available):
    import os

    env = os.environ.copy()
    env["REDIS_URL"] = TEST_REDIS_URL
    env["CELERY_BROKER_URL"] = TEST_REDIS_URL
    env["CELERY_RESULT_BACKEND"] = TEST_REDIS_URL

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "app.worker.celery_app",
            "worker",
            "--loglevel=info",
            "--pool=solo",
            "-Q",
            "system",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    # Continuously drain stdout for the subprocess's whole lifetime, not
    # just until "ready" -- an undrained OS pipe fills once the worker logs
    # enough, which blocks the child's next write() and hangs it silently.
    # See test_process_document_real_redis.py for the fuller account of
    # this (found there, applied back here for the same latent risk).
    output_lines: list[str] = []
    ready_event = threading.Event()

    def _drain_output():
        for line in process.stdout:
            output_lines.append(line)
            if "ready" in line.lower():
                ready_event.set()

    reader_thread = threading.Thread(target=_drain_output, daemon=True)
    reader_thread.start()

    ready = ready_event.wait(timeout=30)

    if not ready:
        process.terminate()
        process.wait(timeout=10)
        pytest.fail(
            "Celery worker subprocess never reported ready:\n"
            + "".join(output_lines)
        )

    yield process

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    reader_thread.join(timeout=5)


def test_health_check_executes_via_a_real_worker_process(worker_process):
    # Re-import bound to the same (env-patched) celery_app module state.
    from app.worker.tasks.system import health_check

    async_result = health_check.delay()
    value = async_result.get(timeout=15)

    assert value == {"status": "ok", "retries": 0}
    assert async_result.successful()


def test_permanent_failure_fails_via_a_real_worker_without_retrying(worker_process):
    from app.worker.tasks.system import health_check

    async_result = health_check.delay(simulate_failure="permanent")

    with pytest.raises(Exception) as exc_info:
        async_result.get(timeout=15)

    assert "Simulated permanent failure" in str(exc_info.value)
    assert async_result.failed()
