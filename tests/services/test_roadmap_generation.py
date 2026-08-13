"""RoadmapGenerationService tests -- see PHASE_09_SEMESTER_ROADMAP.md.

The edit-preservation rule (a regenerate must never silently overwrite a
student's manual edit) is the one the phase brief itself flags as "most
likely to regress silently" and requires a direct test for --
test_regenerate_preserves_user_edited_items below is that test.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.models.roadmap import RoadmapItemOrigin, RoadmapItemType
from app.models.task import Task, TaskStatus, TaskType
from app.repositories.roadmap_repository import RoadmapRepository
from app.schemas.roadmap import RoadmapRecommendationItem, RoadmapRecommendations
from app.services.llm import LLMExtractionError, LLMTransientError
from app.services.roadmap_generation import RoadmapGenerationService
from tests.factories import create_user_with_semester_and_course


class FakeLLMProvider:
    def __init__(self, result: RoadmapRecommendations | None = None, error: Exception | None = None):
        self._result = result if result is not None else RoadmapRecommendations(items=[])
        self._error = error
        self.calls: list[str] = []

    def extract_structured(self, *, system_prompt, content, response_schema):
        self.calls.append(content)
        if self._error is not None:
            raise self._error
        return self._result


def _add_task(db_session, *, course_id, title="Task", due_at, task_type=TaskType.ASSIGNMENT, status=TaskStatus.TODO):
    task = Task(
        course_id=course_id,
        title=title,
        task_type=task_type,
        status=status,
        due_at=due_at,
        is_deleted=False,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _build_service(db_session, *, llm_provider=None):
    repository = RoadmapRepository(db_session)
    service = RoadmapGenerationService(
        db=db_session,
        settings=SimpleNamespace(llm_provider="gemini"),
        roadmap_repository=repository,
        llm_provider=llm_provider,
    )
    return service, repository


def test_generate_creates_deterministic_items_from_real_tasks(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="gen-basic")
    due = datetime(2026, 8, 26, tzinfo=timezone.utc)
    task = _add_task(db_session, course_id=course.id, title="Essay 1", due_at=due, task_type=TaskType.ASSIGNMENT)

    service, repository = _build_service(db_session, llm_provider=FakeLLMProvider())
    roadmap = repository.get_or_create(semester.id)

    roadmap = service.generate(roadmap, semester)

    items = repository.list_items_by_roadmap(roadmap.id)
    deterministic = [i for i in items if i.origin == RoadmapItemOrigin.DETERMINISTIC]
    assert len(deterministic) == 1
    assert deterministic[0].task_id == task.id
    assert deterministic[0].item_type == RoadmapItemType.ASSIGNMENT_PREPARATION
    assert deterministic[0].title == "Work on Essay 1"
    assert deterministic[0].due_date == due.date()


def test_generate_without_llm_provider_completes_with_reason_set(db_session, monkeypatch):
    from app.services.llm import LLMNotConfiguredError

    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="gen-no-llm")
    _add_task(db_session, course_id=course.id, due_at=datetime(2026, 8, 26, tzinfo=timezone.utc))

    def _raise(settings):
        raise LLMNotConfiguredError("LLM_PROVIDER not set")

    monkeypatch.setattr("app.services.roadmap_generation.get_llm_provider", _raise)

    repository = RoadmapRepository(db_session)
    service = RoadmapGenerationService(
        db=db_session,
        settings=SimpleNamespace(llm_provider=None),
        roadmap_repository=repository,
        llm_provider=None,
    )
    roadmap = repository.get_or_create(semester.id)

    roadmap = service.generate(roadmap, semester)

    assert roadmap.recommendations_unavailable_reason is not None
    assert "not available" in roadmap.recommendations_unavailable_reason
    # Deterministic work still happened despite no LLM.
    items = repository.list_items_by_roadmap(roadmap.id)
    assert any(i.origin == RoadmapItemOrigin.DETERMINISTIC for i in items)


def test_generate_persists_valid_recommendation_referencing_a_real_task(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="gen-rec-ok")
    task = _add_task(db_session, course_id=course.id, due_at=datetime(2026, 8, 26, tzinfo=timezone.utc))

    provider = FakeLLMProvider(
        RoadmapRecommendations(
            items=[
                RoadmapRecommendationItem(
                    week_number=1,
                    title="Start early",
                    description="This week has one deadline, get ahead of it.",
                    related_task_id=task.id,
                )
            ]
        )
    )
    service, repository = _build_service(db_session, llm_provider=provider)
    roadmap = repository.get_or_create(semester.id)

    roadmap = service.generate(roadmap, semester)

    items = repository.list_items_by_roadmap(roadmap.id)
    recommendations = [i for i in items if i.origin == RoadmapItemOrigin.AI_GENERATED]
    assert len(recommendations) == 1
    assert recommendations[0].task_id == task.id
    assert recommendations[0].course_id == course.id
    assert recommendations[0].title == "Start early"
    assert roadmap.recommendations_unavailable_reason is None


def test_generate_strips_hallucinated_task_reference_but_keeps_text(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="gen-rec-halluc")
    real_task = _add_task(db_session, course_id=course.id, due_at=datetime(2026, 8, 26, tzinfo=timezone.utc))
    fake_task_id = real_task.id + 999

    provider = FakeLLMProvider(
        RoadmapRecommendations(
            items=[
                RoadmapRecommendationItem(
                    week_number=1,
                    title="Prioritize Biology",
                    description="Some invented claim about a task that was never given.",
                    related_task_id=fake_task_id,
                )
            ]
        )
    )
    service, repository = _build_service(db_session, llm_provider=provider)
    roadmap = repository.get_or_create(semester.id)

    roadmap = service.generate(roadmap, semester)

    recommendations = [
        i for i in repository.list_items_by_roadmap(roadmap.id) if i.origin == RoadmapItemOrigin.AI_GENERATED
    ]
    assert len(recommendations) == 1
    assert recommendations[0].task_id is None
    assert recommendations[0].title == "Prioritize Biology"


def test_generate_drops_recommendation_with_invalid_week_number(db_session):
    user, semester, course = create_user_with_semester_and_course(
        db_session, email_prefix="gen-rec-badweek",
        semester_start=date(2026, 8, 24),
        semester_end=date(2026, 8, 30),  # exactly 1 week
    )
    _add_task(db_session, course_id=course.id, due_at=datetime(2026, 8, 26, tzinfo=timezone.utc))

    provider = FakeLLMProvider(
        RoadmapRecommendations(
            items=[
                RoadmapRecommendationItem(
                    week_number=99,  # doesn't exist -- only week 1 does
                    title="Invented week",
                    description="Should never be persisted.",
                )
            ]
        )
    )
    service, repository = _build_service(db_session, llm_provider=provider)
    roadmap = repository.get_or_create(semester.id)

    roadmap = service.generate(roadmap, semester)

    recommendations = [
        i for i in repository.list_items_by_roadmap(roadmap.id) if i.origin == RoadmapItemOrigin.AI_GENERATED
    ]
    assert recommendations == []


def test_generate_handles_llm_transient_error_without_failing_the_roadmap(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="gen-transient")
    _add_task(db_session, course_id=course.id, due_at=datetime(2026, 8, 26, tzinfo=timezone.utc))

    provider = FakeLLMProvider(error=LLMTransientError("rate limited"))
    service, repository = _build_service(db_session, llm_provider=provider)
    roadmap = repository.get_or_create(semester.id)

    roadmap = service.generate(roadmap, semester)

    assert roadmap.recommendations_unavailable_reason is not None
    deterministic = [
        i for i in repository.list_items_by_roadmap(roadmap.id) if i.origin == RoadmapItemOrigin.DETERMINISTIC
    ]
    assert len(deterministic) == 1  # deterministic pass unaffected


def test_generate_handles_llm_extraction_error_without_failing_the_roadmap(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="gen-extract-err")
    _add_task(db_session, course_id=course.id, due_at=datetime(2026, 8, 26, tzinfo=timezone.utc))

    provider = FakeLLMProvider(error=LLMExtractionError("bad schema"))
    service, repository = _build_service(db_session, llm_provider=provider)
    roadmap = repository.get_or_create(semester.id)

    roadmap = service.generate(roadmap, semester)

    assert roadmap.recommendations_unavailable_reason is not None


def test_regenerate_preserves_user_edited_items(db_session):
    """The mandatory edit-preservation test. A student edits a deterministic
    item; the underlying task then changes (different due date/title);
    regenerating must leave the edited item exactly as the student left it."""
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="gen-edit-preserve")
    task = _add_task(
        db_session, course_id=course.id, title="Essay 1",
        due_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    service, repository = _build_service(db_session, llm_provider=FakeLLMProvider())
    roadmap = repository.get_or_create(semester.id)
    roadmap = service.generate(roadmap, semester)

    items = repository.list_items_by_roadmap(roadmap.id)
    deterministic_item = next(i for i in items if i.origin == RoadmapItemOrigin.DETERMINISTIC)

    # Student edits the item's title.
    repository.update_item(deterministic_item, title="My custom prep plan", description="Do X then Y.")
    assert deterministic_item.is_user_edited is True

    # The underlying task changes (e.g. the professor moved the deadline).
    task.title = "Essay 1 (revised)"
    task.due_at = datetime(2026, 9, 2, tzinfo=timezone.utc)
    db_session.commit()

    roadmap = service.generate(roadmap, semester)

    items_after = repository.list_items_by_roadmap(roadmap.id)
    same_item = next(i for i in items_after if i.id == deterministic_item.id)

    assert same_item.title == "My custom prep plan"
    assert same_item.description == "Do X then Y."
    assert same_item.is_user_edited is True
    # Untouched by the task's due-date change -- regeneration didn't move it.
    assert same_item.due_date == datetime(2026, 8, 26, tzinfo=timezone.utc).date()


def test_regenerate_updates_non_edited_deterministic_items_in_place(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="gen-update-inplace")
    task = _add_task(
        db_session, course_id=course.id, title="Essay 1",
        due_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    service, repository = _build_service(db_session, llm_provider=FakeLLMProvider())
    roadmap = repository.get_or_create(semester.id)
    roadmap = service.generate(roadmap, semester)

    task.due_at = datetime(2026, 9, 2, tzinfo=timezone.utc)
    db_session.commit()

    roadmap = service.generate(roadmap, semester)

    items = repository.list_items_by_roadmap(roadmap.id)
    deterministic = [i for i in items if i.origin == RoadmapItemOrigin.DETERMINISTIC]
    assert len(deterministic) == 1
    assert deterministic[0].due_date == datetime(2026, 9, 2, tzinfo=timezone.utc).date()


def test_regenerate_removes_stale_deterministic_items_unless_edited(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="gen-stale")
    task_a = _add_task(db_session, course_id=course.id, title="Keep editing", due_at=datetime(2026, 8, 26, tzinfo=timezone.utc))
    task_b = _add_task(db_session, course_id=course.id, title="Will be completed", due_at=datetime(2026, 8, 27, tzinfo=timezone.utc))

    service, repository = _build_service(db_session, llm_provider=FakeLLMProvider())
    roadmap = repository.get_or_create(semester.id)
    roadmap = service.generate(roadmap, semester)

    items = repository.list_items_by_roadmap(roadmap.id)
    item_a = next(i for i in items if i.task_id == task_a.id)
    repository.update_item(item_a, title="Edited", description=None)

    # task_b gets completed -- no longer needs prep.
    task_b.status = TaskStatus.COMPLETED
    db_session.commit()

    roadmap = service.generate(roadmap, semester)

    items_after = repository.list_items_by_roadmap(roadmap.id)
    deterministic_after = [i for i in items_after if i.origin == RoadmapItemOrigin.DETERMINISTIC]
    task_ids_after = {i.task_id for i in deterministic_after}

    assert task_a.id in task_ids_after  # preserved (edited)
    assert task_b.id not in task_ids_after  # removed (completed, never edited)


def test_regenerate_increments_version_each_successful_pass(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="gen-version")
    _add_task(db_session, course_id=course.id, due_at=datetime(2026, 8, 26, tzinfo=timezone.utc))

    service, repository = _build_service(db_session, llm_provider=FakeLLMProvider())
    roadmap = repository.get_or_create(semester.id)
    assert roadmap.version == 0

    roadmap = service.generate(roadmap, semester)
    assert roadmap.version == 1

    roadmap = service.generate(roadmap, semester)
    assert roadmap.version == 2


def test_generate_handles_multiple_courses_and_conflicting_deadlines(db_session):
    """Realistic integrated scenario: a student with tasks across more than
    one course, including two deadlines landing in the same week -- the
    roadmap must surface both, grounded in real task/course data, with no
    invented deadlines."""
    user, semester, course_a = create_user_with_semester_and_course(
        db_session, email_prefix="gen-multi", course_code="CS101", course_name="Intro to CS"
    )
    from app.models.course import Course, CourseStatus

    course_b = Course(
        semester_id=semester.id, course_code="MATH201", name="Calculus II",
        credits=3, status=CourseStatus.ACTIVE, is_deleted=False,
    )
    db_session.add(course_b)
    db_session.commit()
    db_session.refresh(course_b)

    same_week_due = datetime(2026, 8, 26, tzinfo=timezone.utc)
    task_cs = _add_task(db_session, course_id=course_a.id, title="CS Essay", due_at=same_week_due, task_type=TaskType.ASSIGNMENT)
    task_math = _add_task(db_session, course_id=course_b.id, title="Calc Midterm", due_at=same_week_due, task_type=TaskType.EXAM)

    service, repository = _build_service(db_session, llm_provider=FakeLLMProvider())
    roadmap = repository.get_or_create(semester.id)
    roadmap = service.generate(roadmap, semester)

    items = repository.list_items_by_roadmap(roadmap.id)
    deterministic = [i for i in items if i.origin == RoadmapItemOrigin.DETERMINISTIC]
    task_ids = {i.task_id for i in deterministic}

    assert task_cs.id in task_ids
    assert task_math.id in task_ids
    course_ids = {i.course_id for i in deterministic}
    assert course_ids == {course_a.id, course_b.id}
    # Both land in the same week -- the roadmap doesn't merge or hide either.
    weeks_used = {i.week_id for i in deterministic}
    assert len(weeks_used) == 1
