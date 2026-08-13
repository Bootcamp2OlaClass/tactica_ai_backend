"""RoadmapRepository ownership/isolation and atomic-claim tests -- see
PHASE_09_SEMESTER_ROADMAP.md's security requirement (same ownership
discipline as every other object) and the Phase 05-08 atomic-claim
convention this phase's Celery task reuses.
"""

from datetime import date, datetime, timezone

from app.models.roadmap import RoadmapGenerationStatus
from app.models.task import Task, TaskStatus, TaskType
from app.repositories.roadmap_repository import RoadmapRepository
from tests.factories import create_user_with_semester_and_course


def _add_task(db_session, *, course_id, due_at):
    task = Task(
        course_id=course_id,
        title="Task",
        task_type=TaskType.ASSIGNMENT,
        status=TaskStatus.TODO,
        due_at=due_at,
        is_deleted=False,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _generate_minimal_roadmap(db_session, *, semester, course):
    """Produces one real RoadmapItem via the repository's own week/item
    helpers, without going through the full generation service -- enough
    for these repository-focused tests."""
    repository = RoadmapRepository(db_session)
    roadmap = repository.get_or_create(semester.id)
    week = repository.get_or_create_week(
        roadmap_id=roadmap.id, week_number=1,
        start_date=semester.start_date, end_date=semester.end_date,
    )
    task = _add_task(db_session, course_id=course.id, due_at=datetime.combine(semester.start_date, datetime.min.time(), tzinfo=timezone.utc))

    from app.models.roadmap import RoadmapItem, RoadmapItemOrigin, RoadmapItemType

    item = RoadmapItem(
        week_id=week.id, roadmap_id=roadmap.id,
        item_type=RoadmapItemType.MILESTONE, origin=RoadmapItemOrigin.DETERMINISTIC,
        title="Item", task_id=task.id, course_id=course.id, due_date=semester.start_date,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return repository, roadmap, item


def test_get_item_owned_returns_none_for_another_users_item(db_session):
    user_a, semester_a, course_a = create_user_with_semester_and_course(db_session, email_prefix="road-a")
    user_b, semester_b, course_b = create_user_with_semester_and_course(db_session, email_prefix="road-b")

    repository, roadmap, item = _generate_minimal_roadmap(db_session, semester=semester_a, course=course_a)

    assert repository.get_item_owned(item_id=item.id, user_id=user_b.id) is None
    assert repository.get_item_owned(item_id=item.id, user_id=user_a.id) is not None


def test_get_by_semester_id_is_naturally_scoped_by_the_callers_own_semester(db_session):
    # get_by_semester_id itself doesn't check ownership (semester_id is
    # already the caller's own, verified one level up by
    # RoadmapQueryService/RoadmapGenerationTriggerService via
    # SemesterRepository.get_by_id_and_owner) -- this test documents that
    # division of responsibility rather than re-testing the service layer.
    user_a, semester_a, course_a = create_user_with_semester_and_course(db_session, email_prefix="road-scope-a")
    user_b, semester_b, course_b = create_user_with_semester_and_course(db_session, email_prefix="road-scope-b")

    repository = RoadmapRepository(db_session)
    roadmap_a = repository.get_or_create(semester_a.id)
    roadmap_b = repository.get_or_create(semester_b.id)

    assert repository.get_by_semester_id(semester_a.id).id == roadmap_a.id
    assert repository.get_by_semester_id(semester_b.id).id == roadmap_b.id
    assert roadmap_a.id != roadmap_b.id


def test_try_start_generation_claims_a_not_requested_roadmap(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="road-claim")
    repository = RoadmapRepository(db_session)
    roadmap = repository.get_or_create(semester.id)

    assert repository.try_start_generation(roadmap.id) is True

    db_session.refresh(roadmap)
    assert roadmap.status == RoadmapGenerationStatus.PROCESSING


def test_try_start_generation_cannot_claim_an_already_processing_roadmap(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="road-claim-dup")
    repository = RoadmapRepository(db_session)
    roadmap = repository.get_or_create(semester.id)

    assert repository.try_start_generation(roadmap.id) is True
    # A second, genuinely concurrent claim attempt must fail.
    assert repository.try_start_generation(roadmap.id) is False


def test_try_start_generation_can_reclaim_a_failed_roadmap(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="road-claim-retry")
    repository = RoadmapRepository(db_session)
    roadmap = repository.get_or_create(semester.id)

    repository.try_start_generation(roadmap.id)
    repository.mark_failed(roadmap, "boom")

    assert repository.try_start_generation(roadmap.id) is True


def test_update_item_sets_is_user_edited_and_persists_fields(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="road-update")
    repository, roadmap, item = _generate_minimal_roadmap(db_session, semester=semester, course=course)

    assert item.is_user_edited is False

    updated = repository.update_item(item, title="New title", description="New description")

    assert updated.title == "New title"
    assert updated.description == "New description"
    assert updated.is_user_edited is True
