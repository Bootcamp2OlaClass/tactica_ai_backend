from datetime import date, datetime, timedelta, timezone

from app.models.course import Course, CourseStatus
from app.models.semester import Semester, SemesterStatus
from app.models.task import (
    TaskPriority,
    TaskStatus,
    TaskType,
)
from app.models.user import User, UserRole
from app.repositories.task_repository import (
    count_tasks,
    create_task,
    get_task_by_id,
    list_tasks,
    mark_task_completed,
    reopen_task,
    soft_delete_task,
    update_task,
)

def create_test_user(
    db_session,
    *,
    email: str,
) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        full_name="Test User",
        role=UserRole.STUDENT,
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return user


def create_test_semester(
    db_session,
    *,
    user_id: int,
    name: str = "Fall 2026",
) -> Semester:
    semester = Semester(
        user_id=user_id,
        name=name,
        academic_year=2026,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 15),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )

    db_session.add(semester)
    db_session.commit()
    db_session.refresh(semester)

    return semester


def create_test_course(
    db_session,
    *,
    semester_id: int,
    course_code: str = "COSC-1437",
) -> Course:
    course = Course(
        semester_id=semester_id,
        course_code=course_code,
        name="Programming Fundamentals II",
        credits=4,
        status=CourseStatus.ACTIVE,
        is_deleted=False,
    )

    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)

    return course

def test_create_task(db_session):
    user = create_test_user(
        db_session,
        email="task-create@example.com",
    )

    semester = create_test_semester(
        db_session,
        user_id=user.id,
    )

    course = create_test_course(
        db_session,
        semester_id=semester.id,
    )

    task = create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Complete Python assignment",
            "description": "Finish repository exercises",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.TODO,
            "priority": TaskPriority.HIGH,
            "due_at": datetime(
                2026,
                9,
                15,
                23,
                59,
                tzinfo=timezone.utc,
            ),
        },
    )

    assert task.id is not None
    assert task.course_id == course.id
    assert task.title == "Complete Python assignment"
    assert task.status == TaskStatus.TODO
    assert task.priority == TaskPriority.HIGH

def test_get_task_by_id(db_session):
    owner = create_test_user(
        db_session,
        email="owner@example.com",
    )

    other_user = create_test_user(
        db_session,
        email="other@example.com",
    )

    semester = create_test_semester(
        db_session,
        user_id=owner.id,
    )

    course = create_test_course(
        db_session,
        semester_id=semester.id,
    )

    task = create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Assignment",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.TODO,
            "priority": TaskPriority.MEDIUM,
        },
    )

    owner_result = get_task_by_id(
        db=db_session,
        task_id=task.id,
        user_id=owner.id,
    )

    other_result = get_task_by_id(
        db=db_session,
        task_id=task.id,
        user_id=other_user.id,
    )

    assert owner_result is not None
    assert owner_result.id == task.id
    assert other_result is None

def test_update_task(db_session):
    user = create_test_user(
        db_session,
        email="update@example.com",
    )

    semester = create_test_semester(
        db_session,
        user_id=user.id,
    )

    course = create_test_course(
        db_session,
        semester_id=semester.id,
    )

    task = create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Old title",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.TODO,
            "priority": TaskPriority.LOW,
        },
    )

    updated = update_task(
        db=db_session,
        task=task,
        update_data={
            "title": "New title",
            "priority": TaskPriority.HIGH,
        },
    )

    assert updated.title == "New title"
    assert updated.priority == TaskPriority.HIGH

def test_soft_delete_task(db_session):
    user = create_test_user(
        db_session,
        email="delete@example.com",
    )

    semester = create_test_semester(
        db_session,
        user_id=user.id,
    )

    course = create_test_course(
        db_session,
        semester_id=semester.id,
    )

    task = create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Delete me",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.TODO,
            "priority": TaskPriority.LOW,
        },
    )

    deleted = soft_delete_task(
        db=db_session,
        task=task,
    )

    assert deleted.is_deleted is True
    assert deleted.deleted_at is not None

    result = get_task_by_id(
        db=db_session,
        task_id=task.id,
        user_id=user.id,
    )

    assert result is None

def test_mark_task_completed(db_session):
    user = create_test_user(
        db_session,
        email="complete@example.com",
    )

    semester = create_test_semester(
        db_session,
        user_id=user.id,
    )

    course = create_test_course(
        db_session,
        semester_id=semester.id,
    )

    task = create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Complete me",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.TODO,
            "priority": TaskPriority.MEDIUM,
        },
    )

    completed_at = datetime(
        2026,
        9,
        1,
        12,
        0,
        tzinfo=timezone.utc,
    )

    completed = mark_task_completed(
        db=db_session,
        task=task,
        completed_at=completed_at,
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.completed_at == completed_at


def test_reopen_task(db_session):
    user = create_test_user(
        db_session,
        email="reopen@example.com",
    )

    semester = create_test_semester(
        db_session,
        user_id=user.id,
    )

    course = create_test_course(
        db_session,
        semester_id=semester.id,
    )

    task = create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Reopen me",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.COMPLETED,
            "priority": TaskPriority.MEDIUM,
            "completed_at": datetime(
                2026,
                9,
                1,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        },
    )

    reopened = reopen_task(
        db=db_session,
        task=task,
    )

    assert reopened.status == TaskStatus.TODO
    assert reopened.completed_at is None


def test_list_tasks_filters_and_search(db_session):
    user = create_test_user(
        db_session,
        email="list-task@example.com",
    )

    semester = create_test_semester(
        db_session,
        user_id=user.id,
    )

    course = create_test_course(
        db_session,
        semester_id=semester.id,
    )

    create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Calculus homework",
            "description": "Complete derivatives worksheet",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.TODO,
            "priority": TaskPriority.HIGH,
        },
    )

    create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Python exam",
            "description": "Review classes and inheritance",
            "task_type": TaskType.EXAM,
            "status": TaskStatus.IN_PROGRESS,
            "priority": TaskPriority.URGENT,
        },
    )

    results = list_tasks(
        db=db_session,
        user_id=user.id,
        course_id=course.id,
        status=TaskStatus.TODO,
        priority=TaskPriority.HIGH,
        task_type=TaskType.ASSIGNMENT,
        search="derivatives",
    )

    assert len(results) == 1
    assert results[0].title == "Calculus homework"


def test_count_tasks_and_overdue_filter(db_session):
    user = create_test_user(
        db_session,
        email="count-task@example.com",
    )

    semester = create_test_semester(
        db_session,
        user_id=user.id,
    )

    course = create_test_course(
        db_session,
        semester_id=semester.id,
    )

    current_time = datetime(
        2026,
        9,
        10,
        12,
        0,
        tzinfo=timezone.utc,
    )

    create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Overdue task",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.TODO,
            "priority": TaskPriority.HIGH,
            "due_at": current_time - timedelta(days=1),
        },
    )

    create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Completed past task",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.COMPLETED,
            "priority": TaskPriority.MEDIUM,
            "due_at": current_time - timedelta(days=2),
            "completed_at": current_time - timedelta(days=1),
        },
    )

    create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Future task",
            "task_type": TaskType.QUIZ,
            "status": TaskStatus.TODO,
            "priority": TaskPriority.LOW,
            "due_at": current_time + timedelta(days=1),
        },
    )

    overdue_items = list_tasks(
        db=db_session,
        user_id=user.id,
        overdue=True,
        current_time=current_time,
    )

    overdue_count = count_tasks(
        db=db_session,
        user_id=user.id,
        overdue=True,
        current_time=current_time,
    )

    assert len(overdue_items) == 1
    assert overdue_items[0].title == "Overdue task"
    assert overdue_count == 1

def test_list_tasks_overdue_filter_excludes_completed_and_cancelled(
    db_session,
):
    user = create_test_user(
        db_session,
        email="overdue-filter@example.com",
    )

    semester = create_test_semester(
        db_session,
        user_id=user.id,
    )

    course = create_test_course(
        db_session,
        semester_id=semester.id,
    )

    current_time = datetime(
        2026,
        9,
        10,
        12,
        0,
        tzinfo=timezone.utc,
    )

    overdue_task = create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Overdue assignment",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.TODO,
            "priority": TaskPriority.HIGH,
            "due_at": current_time - timedelta(days=1),
        },
    )

    create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Completed old assignment",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.COMPLETED,
            "priority": TaskPriority.MEDIUM,
            "due_at": current_time - timedelta(days=2),
            "completed_at": current_time - timedelta(days=1),
        },
    )

    create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Cancelled old assignment",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.CANCELLED,
            "priority": TaskPriority.LOW,
            "due_at": current_time - timedelta(days=3),
        },
    )

    create_task(
        db=db_session,
        task_data={
            "course_id": course.id,
            "title": "Future assignment",
            "task_type": TaskType.ASSIGNMENT,
            "status": TaskStatus.TODO,
            "priority": TaskPriority.MEDIUM,
            "due_at": current_time + timedelta(days=1),
        },
    )

    results = list_tasks(
        db=db_session,
        user_id=user.id,
        overdue=True,
        current_time=current_time,
    )

    assert len(results) == 1
    assert results[0].id == overdue_task.id