"""Real integration test for the document-processing pipeline: test
process -> Redis -> a genuine separate `celery worker` subprocess ->
process_document -> real database status changes + a real extracted-text
artifact persisted via StorageProvider.

Same pattern as test_health_check_real_redis.py (Phase 04) -- dedicated
disposable Redis on port 6380, auto-skipped if unreachable rather than
failing the suite. Explicitly does NOT rely on fixture ordering for the
worker subprocess's database env vars (module-scoped fixtures can run
before the function-scoped, autouse `database_environment` fixture) --
they're set directly from the same constants conftest.py uses.
"""

import os
import subprocess
import sys
import threading
import time

import pytest

from app.worker.celery_app import celery_app
from tests.conftest import TEST_DATABASE_PORT, TEST_DATABASE_URL
from tests.factories import create_document

TEST_REDIS_URL = "redis://localhost:6380/2"


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
    # See test_health_check_real_redis.py for why the cached pool/backend
    # must be explicitly reset, not just the config values.
    original_broker = celery_app.conf.broker_url
    original_backend = celery_app.conf.result_backend
    celery_app.conf.broker_url = TEST_REDIS_URL
    celery_app.conf.result_backend = TEST_REDIS_URL
    celery_app._pool = None
    celery_app._backend_cache = None
    celery_app._local.__dict__.pop("backend", None)
    # `amqp` is a cached_property (stored directly in __dict__) that holds
    # the publish-side Producer/connection machinery -- found the hard way:
    # resetting only _pool/_backend_cache left .delay() silently publishing
    # through a Producer still bound to whichever broker was active when
    # `amqp` was first accessed (e.g. by another real-Redis test module
    # earlier in the same session), so the worker (correctly connected to
    # *this* test's Redis) never received the message and every .get()
    # timed out with no error -- not a worker hang, a client-side stale cache.
    celery_app.__dict__.pop("amqp", None)
    yield
    celery_app.conf.broker_url = original_broker
    celery_app.conf.result_backend = original_backend
    celery_app._pool = None
    celery_app._backend_cache = None
    celery_app._local.__dict__.pop("backend", None)
    celery_app.__dict__.pop("amqp", None)


@pytest.fixture(scope="module")
def worker_process(redis_available, tmp_path_factory):
    upload_dir = tmp_path_factory.mktemp("worker-storage")

    env = os.environ.copy()
    env["REDIS_URL"] = TEST_REDIS_URL
    env["CELERY_BROKER_URL"] = TEST_REDIS_URL
    env["CELERY_RESULT_BACKEND"] = TEST_REDIS_URL
    env["DATABASE_HOST"] = "127.0.0.1"
    env["DATABASE_PORT"] = TEST_DATABASE_PORT
    env["DATABASE_NAME"] = "test_database"
    env["DATABASE_USER"] = "test_user"
    env["DATABASE_PASSWORD"] = "test_password"
    env["DATABASE_URL"] = TEST_DATABASE_URL
    env["JWT_SECRET"] = "test-secret-key"
    env["STORAGE_PROVIDER"] = "local"
    env["UPLOAD_DIR"] = str(upload_dir)

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
            "documents",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    # Continuously drain stdout for the subprocess's whole lifetime, not
    # just until "ready" -- an undrained OS pipe fills once the worker logs
    # enough (every processed task does), which blocks the child's next
    # write() and hangs it silently. This bit Phase 04's health_check test
    # too, just not obviously (tiny log volume); process_document logs
    # enough per task to hit it reliably once a real PDF is processed.
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
            "Celery worker subprocess never reported ready:\n" + "".join(output_lines)
        )

    yield process, upload_dir, output_lines

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    reader_thread.join(timeout=5)


def _pdf_bytes(text: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    return bytes(pdf.output())


def test_process_document_executes_via_a_real_worker_and_persists_result(
    db_session, worker_process
):
    from app.models.document import ExtractionMethod, ProcessingStatus
    from app.services.storage.local import LocalStorageProvider
    from app.worker.tasks.documents import process_document

    _worker, upload_dir, _worker_output_lines = worker_process

    # Save the PDF through the *same* LocalStorageProvider directory the
    # worker subprocess is configured to read from (its own UPLOAD_DIR).
    storage = LocalStorageProvider(str(upload_dir))
    pdf_bytes = _pdf_bytes("Real worker integration test syllabus content.")
    storage_path = storage.save(pdf_bytes, "courses/1/documents/real-worker-test.pdf")

    document = create_document(
        db_session,
        storage_path=storage_path,
        stored_file_name="real-worker-test.pdf",
    )

    async_result = process_document.delay(document.id)
    result = async_result.get(timeout=20)

    assert result["status"] == "completed"
    assert async_result.successful()

    db_session.refresh(document)
    assert document.processing_status == ProcessingStatus.COMPLETED
    assert document.extraction_method == ExtractionMethod.NATIVE
    assert document.page_count == 1
    assert document.extracted_content_path is not None

    artifact_bytes = storage.load(document.extracted_content_path)
    assert b"Real worker integration test" in artifact_bytes
