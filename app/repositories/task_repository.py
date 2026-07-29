from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.semester import Semester
from app.models.task import (
    Task,
    TaskPriority,
    TaskStatus,
    TaskType,
)


def create_task(
    db: Session,
    task_data: dict,
) -> Task:
    task = Task(**task_data)

    db.add(task)
    db.commit()
    db.refresh(task)

    return task


def get_task_by_id(
    db: Session,
    task_id: int,
    user_id: int,
) -> Task | None:
    return (
        db.query(Task)
        .join(
            Course,
            Task.course_id == Course.id,
        )
        .join(
            Semester,
            Course.semester_id == Semester.id,
        )
        .filter(
            Task.id == task_id,
            Semester.user_id == user_id,
            Task.is_deleted.is_(False),
            Course.is_deleted.is_(False),
            Semester.is_deleted.is_(False),
        )
        .first()
    )


def list_tasks(
    db: Session,
    user_id: int,
    offset: int = 0,
    limit: int = 20,
    course_id: int | None = None,
    semester_id: int | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    task_type: TaskType | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    overdue: bool | None = None,
    current_time: datetime | None = None,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> list[Task]:
    query = (
        db.query(Task)
        .join(
            Course,
            Task.course_id == Course.id,
        )
        .join(
            Semester,
            Course.semester_id == Semester.id,
        )
        .filter(
            Semester.user_id == user_id,
            Task.is_deleted.is_(False),
            Course.is_deleted.is_(False),
            Semester.is_deleted.is_(False),
        )
    )

    if course_id is not None:
        query = query.filter(
            Task.course_id == course_id,
        )

    if semester_id is not None:
        query = query.filter(
            Course.semester_id == semester_id,
        )

    if status is not None:
        query = query.filter(
            Task.status == status,
        )

    if priority is not None:
        query = query.filter(
            Task.priority == priority,
        )

    if task_type is not None:
        query = query.filter(
            Task.task_type == task_type,
        )

    if due_from is not None:
        query = query.filter(
            Task.due_at >= due_from,
        )

    if due_to is not None:
        query = query.filter(
            Task.due_at <= due_to,
        )

    if overdue is not None:
        now = current_time or datetime.now(timezone.utc)

        if overdue:
            query = query.filter(
                Task.due_at.is_not(None),
                Task.due_at < now,
                Task.status.notin_(
                    [
                        TaskStatus.COMPLETED,
                        TaskStatus.CANCELLED,
                    ]
                ),
            )
        else:
            query = query.filter(
                or_(
                    Task.due_at.is_(None),
                    Task.due_at >= now,
                    Task.status.in_(
                        [
                            TaskStatus.COMPLETED,
                            TaskStatus.CANCELLED,
                        ]
                    ),
                )
            )

    normalized_search = search.strip() if search else ""

    if normalized_search:
        search_value = f"%{normalized_search}%"

        query = query.filter(
            or_(
                Task.title.ilike(search_value),
                Task.description.ilike(search_value),
            )
        )

    allowed_sort_fields = {
        "title": Task.title,
        "status": Task.status,
        "priority": Task.priority,
        "task_type": Task.task_type,
        "due_at": Task.due_at,
        "created_at": Task.created_at,
        "updated_at": Task.updated_at,
    }

    sort_column = allowed_sort_fields.get(
        sort_by,
        Task.created_at,
    )

    if sort_order.lower() == "asc":
        query = query.order_by(
            sort_column.asc(),
            Task.id.asc(),
        )
    else:
        query = query.order_by(
            sort_column.desc(),
            Task.id.desc(),
        )

    return (
        query
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_tasks(
    db: Session,
    user_id: int,
    course_id: int | None = None,
    semester_id: int | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    task_type: TaskType | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    overdue: bool | None = None,
    current_time: datetime | None = None,
    search: str | None = None,
) -> int:
    query = (
        db.query(Task)
        .join(
            Course,
            Task.course_id == Course.id,
        )
        .join(
            Semester,
            Course.semester_id == Semester.id,
        )
        .filter(
            Semester.user_id == user_id,
            Task.is_deleted.is_(False),
            Course.is_deleted.is_(False),
            Semester.is_deleted.is_(False),
        )
    )

    if course_id is not None:
        query = query.filter(
            Task.course_id == course_id,
        )

    if semester_id is not None:
        query = query.filter(
            Course.semester_id == semester_id,
        )

    if status is not None:
        query = query.filter(
            Task.status == status,
        )

    if priority is not None:
        query = query.filter(
            Task.priority == priority,
        )

    if task_type is not None:
        query = query.filter(
            Task.task_type == task_type,
        )

    if due_from is not None:
        query = query.filter(
            Task.due_at >= due_from,
        )

    if due_to is not None:
        query = query.filter(
            Task.due_at <= due_to,
        )

    if overdue is not None:
        now = current_time or datetime.now(timezone.utc)

        if overdue:
            query = query.filter(
                Task.due_at.is_not(None),
                Task.due_at < now,
                Task.status.notin_(
                    [
                        TaskStatus.COMPLETED,
                        TaskStatus.CANCELLED,
                    ]
                ),
            )
        else:
            query = query.filter(
                or_(
                    Task.due_at.is_(None),
                    Task.due_at >= now,
                    Task.status.in_(
                        [
                            TaskStatus.COMPLETED,
                            TaskStatus.CANCELLED,
                        ]
                    ),
                )
            )

    normalized_search = search.strip() if search else ""

    if normalized_search:
        search_value = f"%{normalized_search}%"

        query = query.filter(
            or_(
                Task.title.ilike(search_value),
                Task.description.ilike(search_value),
            )
        )

    return query.count()


def update_task(
    db: Session,
    task: Task,
    update_data: dict,
) -> Task:
    allowed_fields = {
        "title",
        "description",
        "task_type",
        "status",
        "priority",
        "due_at",
        "estimated_minutes",
        "source",
        "source_document_id",
    }

    for field, value in update_data.items():
        if field in allowed_fields:
            setattr(task, field, value)

    db.commit()
    db.refresh(task)

    return task


def mark_task_completed(
    db: Session,
    task: Task,
    completed_at: datetime,
) -> Task:
    task.status = TaskStatus.COMPLETED
    task.completed_at = completed_at

    db.commit()
    db.refresh(task)

    return task


def reopen_task(
    db: Session,
    task: Task,
) -> Task:
    task.status = TaskStatus.TODO
    task.completed_at = None

    db.commit()
    db.refresh(task)

    return task


def soft_delete_task(
    db: Session,
    task: Task,
) -> Task:
    task.is_deleted = True
    task.deleted_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(task)

    return task