from datetime import datetime, timedelta, timezone

from app.models.task import Task, TaskPriority, TaskStatus, TaskType
from app.models.user import User, UserRole
from app.services.academic_context import AcademicContextService
from tests.factories import create_user_with_course


def _add_task(db_session, *, course_id, title, due_at, status=TaskStatus.TODO):
    task = Task(
        course_id=course_id,
        title=title,
        task_type=TaskType.ASSIGNMENT,
        status=status,
        priority=TaskPriority.MEDIUM,
        due_at=due_at,
        is_deleted=False,
    )
    db_session.add(task)
    db_session.commit()
    return task


def test_get_context_reflects_active_courses_and_upcoming_deadlines(db_session):
    user, course = create_user_with_course(db_session, email_prefix="ctx")
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    _add_task(
        db_session,
        course_id=course.id,
        title="Homework 3",
        due_at=now + timedelta(days=3),
    )

    service = AcademicContextService(db_session)
    context = service.get_context(user_id=user.id, current_time=now)

    assert context.course_names == [f"{course.course_code} - {course.name}"]
    assert any("Homework 3" in item for item in context.upcoming_deadlines)
    assert not context.is_empty()


def test_get_context_counts_overdue_tasks(db_session):
    user, course = create_user_with_course(db_session, email_prefix="ctx-overdue")
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    _add_task(
        db_session,
        course_id=course.id,
        title="Late Reading",
        due_at=now - timedelta(days=2),
    )

    service = AcademicContextService(db_session)
    context = service.get_context(user_id=user.id, current_time=now)

    assert context.overdue_count == 1
    # Overdue tasks aren't "upcoming" -- they must not appear in both buckets.
    assert not any("Late Reading" in item for item in context.upcoming_deadlines)


def test_get_context_is_empty_for_a_brand_new_account(db_session):
    # Deliberately a bare User with no Semester/Course at all (not
    # create_user_with_course, which always creates one course) -- this
    # is the case ChatService's deterministic short-circuit depends on.
    user = User(
        email=f"ctx-empty-{id(db_session)}@example.com",
        password_hash="hashed-password",
        full_name="Empty Account",
        role=UserRole.STUDENT,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    service = AcademicContextService(db_session)
    context = service.get_context(user_id=user.id)

    assert context.is_empty()
    assert context.course_names == []
    assert context.upcoming_deadlines == []
    assert context.overdue_count == 0


def test_get_context_is_not_empty_when_a_course_exists_even_without_tasks(db_session):
    user, course = create_user_with_course(db_session, email_prefix="ctx-course-only")

    service = AcademicContextService(db_session)
    context = service.get_context(user_id=user.id)

    assert not context.is_empty()
    assert context.course_names == [f"{course.course_code} - {course.name}"]
    assert context.upcoming_deadlines == []
