"""Unit tests for the generate_roadmap task, run in Celery's eager mode
(synchronous, in-process) against a real database -- mirrors
test_embed_document_task.py's / test_extract_document_task.py's pattern.

No LLM provider is configured in this test environment (see
PHASE_09_SEMESTER_ROADMAP.md's NOT VERIFIED note), which is fine here:
these tests are about the task's own idempotency/claim/on_failure
plumbing, not the recommendation pass -- already covered thoroughly
against a fake provider in tests/services/test_roadmap_generation.py.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.roadmap import RoadmapGenerationStatus
from app.models.task import Task, TaskStatus, TaskType
from app.repositories.roadmap_repository import RoadmapRepository
from app.worker.celery_app import celery_app
from app.worker.tasks import roadmap as roadmap_task_module
from app.worker.tasks.roadmap import generate_roadmap
from tests.conftest import TEST_DATABASE_URL
from tests.factories import create_user_with_semester_and_course


@pytest.fixture
def eager_mode():
    original_eager = celery_app.conf.task_always_eager
    original_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager = original_eager
    celery_app.conf.task_eager_propagates = original_propagates


@pytest.fixture(autouse=True)
def task_session_local(monkeypatch):
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    test_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    monkeypatch.setattr(roadmap_task_module, "SessionLocal", test_session_local)
    yield
    engine.dispose()


def _add_task(db_session, *, course_id, due_at):
    task = Task(
        course_id=course_id, title="Essay", task_type=TaskType.ASSIGNMENT,
        status=TaskStatus.TODO, due_at=due_at, is_deleted=False,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_successful_generation_completes_the_roadmap(db_session, eager_mode):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="task-success")
    _add_task(db_session, course_id=course.id, due_at=datetime(2026, 8, 26, tzinfo=timezone.utc))
    repository = RoadmapRepository(db_session)
    roadmap = repository.get_or_create(semester.id)

    result = generate_roadmap.apply(args=[roadmap.id])

    assert result.successful()
    assert result.result["status"] == "completed"

    db_session.refresh(roadmap)
    assert roadmap.status == RoadmapGenerationStatus.COMPLETED
    assert roadmap.version == 1
    items = repository.list_items_by_roadmap(roadmap.id)
    assert len(items) == 1


def test_already_completed_roadmap_is_skipped_idempotently(db_session, eager_mode):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="task-skip")
    repository = RoadmapRepository(db_session)
    roadmap = repository.get_or_create(semester.id)
    roadmap.status = RoadmapGenerationStatus.COMPLETED
    db_session.commit()

    result = generate_roadmap.apply(args=[roadmap.id])

    assert result.successful()
    assert result.result["status"] == "skipped"
    assert result.result["reason"] == "status_completed"


def test_nonexistent_roadmap_is_skipped_without_error(db_session, eager_mode):
    result = generate_roadmap.apply(args=[999999])

    assert result.successful()
    assert result.result["reason"] == "not_found"


def test_unexpected_failure_marks_roadmap_failed_via_on_failure(db_session, eager_mode, monkeypatch):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="task-failure")
    repository = RoadmapRepository(db_session)
    roadmap = repository.get_or_create(semester.id)

    def _boom(self, roadmap, semester):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(
        "app.services.roadmap_generation.RoadmapGenerationService.generate", _boom
    )

    result = generate_roadmap.apply(args=[roadmap.id])

    assert result.failed()
    db_session.refresh(roadmap)
    assert roadmap.status == RoadmapGenerationStatus.FAILED
    assert roadmap.generation_error is not None
