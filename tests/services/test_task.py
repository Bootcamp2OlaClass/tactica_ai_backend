from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.task import (
    TaskConflictError,
    TaskNotFoundError,
    TaskValidationError,
)
from app.models.task import (
    Task,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.task import TaskService

def make_task(
    *,
    task_id: int = 1,
    course_id: int = 10,
    status: TaskStatus = TaskStatus.TODO,
) -> Task:
    task = Task(
        id=task_id,
        course_id=course_id,
        title="Study calculus",
        description="Review chapter 3",
        task_type=TaskType.ASSIGNMENT,
        status=status,
        priority=TaskPriority.MEDIUM,
    )

    return task

@pytest.fixture
def db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(db: MagicMock) -> TaskService:
    return TaskService(db=db)

def test_get_task_returns_owned_task(
    service: TaskService,
) -> None:
    task = make_task()

    with patch(
        "app.services.task.task_repository.get_task_by_id",
        return_value=task,
    ):
        result = service.get_task(
            task_id=1,
            user_id=100,
        )

    assert result is task


def test_get_task_raises_not_found(
    service: TaskService,
) -> None:
    with patch(
        "app.services.task.task_repository.get_task_by_id",
        return_value=None,
    ):
        with pytest.raises(
            TaskNotFoundError,
            match="Task not found.",
        ):
            service.get_task(
                task_id=999,
                user_id=100,
            )


def test_create_task_rejects_completed_status(
    service: TaskService,
) -> None:
    course = MagicMock()

    payload = TaskCreate(
        title="Finish project",
        status=TaskStatus.COMPLETED,
    )

    with patch(
        "app.services.task.course_repository.get_course_by_id",
        return_value=course,
    ):
        with pytest.raises(
            TaskValidationError,
            match="Use the complete operation",
        ):
            service.create_task(
                user_id=100,
                course_id=10,
                task_data=payload,
            )

def test_create_task_success(
    service: TaskService,
) -> None:
    course = MagicMock()

    payload = TaskCreate(
        title="Finish project",
        status=TaskStatus.TODO,
        priority=TaskPriority.HIGH,
    )

    created_task = make_task()

    with (
        patch(
            "app.services.task.course_repository.get_course_by_id",
            return_value=course,
        ),
        patch(
            "app.services.task.task_repository.create_task",
            return_value=created_task,
        ) as create_mock,
    ):
        result = service.create_task(
            user_id=100,
            course_id=10,
            task_data=payload,
        )

    assert result is created_task

    create_mock.assert_called_once()

    sent_payload = create_mock.call_args.kwargs["task_data"]

    assert sent_payload["course_id"] == 10
    assert sent_payload["title"] == "Finish project"
    assert sent_payload["status"] == TaskStatus.TODO
    assert sent_payload["priority"] == TaskPriority.HIGH


def test_create_task_raises_when_course_is_not_owned(
    service: TaskService,
) -> None:
    payload = TaskCreate(
        title="Finish project",
    )

    with patch(
        "app.services.task.course_repository.get_course_by_id",
        return_value=None,
    ):
        with pytest.raises(
            TaskNotFoundError,
            match="Course not found.",
        ):
            service.create_task(
                user_id=100,
                course_id=999,
                task_data=payload,
            )


def test_update_task_success(
    service: TaskService,
) -> None:
    task = make_task()

    payload = TaskUpdate(
        title="Updated task title",
        priority=TaskPriority.URGENT,
    )

    with (
        patch.object(
            service,
            "get_task",
            return_value=task,
        ),
        patch(
            "app.services.task.task_repository.update_task",
            return_value=task,
        ) as update_mock,
    ):
        result = service.update_task(
            task_id=1,
            user_id=100,
            task_data=payload,
        )

    assert result is task

    update_mock.assert_called_once_with(
        db=service.db,
        task=task,
        update_data={
            "title": "Updated task title",
            "priority": TaskPriority.URGENT,
        },
    )


def test_mark_task_completed_success(
    service: TaskService,
) -> None:
    task = make_task(
        status=TaskStatus.TODO,
    )

    completed_task = make_task(
        status=TaskStatus.COMPLETED,
    )
    completed_task.completed_at = datetime.now(timezone.utc)

    with (
        patch.object(
            service,
            "get_task",
            return_value=task,
        ),
        patch(
            "app.services.task.task_repository.mark_task_completed",
            return_value=completed_task,
        ) as complete_mock,
    ):
        result = service.mark_task_completed(
            task_id=1,
            user_id=100,
        )

    assert result is completed_task

    complete_mock.assert_called_once()

    completed_at = complete_mock.call_args.kwargs["completed_at"]

    assert completed_at.tzinfo is not None


def test_mark_cancelled_task_completed_raises_conflict(
    service: TaskService,
) -> None:
    task = make_task(
        status=TaskStatus.CANCELLED,
    )

    with patch.object(
        service,
        "get_task",
        return_value=task,
    ):
        with pytest.raises(
            TaskConflictError,
            match="cancelled task",
        ):
            service.mark_task_completed(
                task_id=1,
                user_id=100,
            )


def test_reopen_completed_task_success(
    service: TaskService,
) -> None:
    task = make_task(
        status=TaskStatus.COMPLETED,
    )
    task.completed_at = datetime.now(timezone.utc)

    reopened_task = make_task(
        status=TaskStatus.TODO,
    )
    reopened_task.completed_at = None

    with (
        patch.object(
            service,
            "get_task",
            return_value=task,
        ),
        patch(
            "app.services.task.task_repository.reopen_task",
            return_value=reopened_task,
        ) as reopen_mock,
    ):
        result = service.reopen_task(
            task_id=1,
            user_id=100,
        )

    assert result is reopened_task

    reopen_mock.assert_called_once_with(
        db=service.db,
        task=task,
    )

def test_list_tasks_returns_paginated_result(
    service: TaskService,
) -> None:
    tasks = [
        make_task(task_id=1),
        make_task(task_id=2),
    ]

    with (
        patch(
            "app.services.task.task_repository.list_tasks",
            return_value=tasks,
        ) as list_mock,
        patch(
            "app.services.task.task_repository.count_tasks",
            return_value=5,
        ) as count_mock,
    ):
        result = service.list_tasks(
            user_id=100,
            page=2,
            page_size=2,
            overdue=True,
            search="calculus",
        )

    assert result == {
        "items": tasks,
        "page": 2,
        "page_size": 2,
        "total": 5,
        "total_pages": 3,
    }

    assert list_mock.call_args.kwargs["offset"] == 2
    assert list_mock.call_args.kwargs["limit"] == 2

    list_current_time = list_mock.call_args.kwargs["current_time"]
    count_current_time = count_mock.call_args.kwargs["current_time"]

    assert list_current_time is count_current_time
    assert list_current_time.tzinfo is not None


def test_list_tasks_rejects_invalid_page(
    service: TaskService,
) -> None:
    with pytest.raises(
        TaskValidationError,
        match="Page must be greater",
    ):
        service.list_tasks(
            user_id=100,
            page=0,
        )


def test_list_tasks_rejects_invalid_page_size(
    service: TaskService,
) -> None:
    with pytest.raises(
        TaskValidationError,
        match="Page size must be greater",
    ):
        service.list_tasks(
            user_id=100,
            page_size=0,
        )


def test_list_tasks_rejects_invalid_due_date_range(
    service: TaskService,
) -> None:
    due_from = datetime(
        2026,
        8,
        20,
        tzinfo=timezone.utc,
    )
    due_to = datetime(
        2026,
        8,
        10,
        tzinfo=timezone.utc,
    )

    with pytest.raises(
        TaskValidationError,
        match="Due-from must be earlier",
    ):
        service.list_tasks(
            user_id=100,
            due_from=due_from,
            due_to=due_to,
        )


def test_mark_completed_is_idempotent(
    service: TaskService,
) -> None:
    task = make_task(
        status=TaskStatus.COMPLETED,
    )
    task.completed_at = datetime.now(timezone.utc)

    with (
        patch.object(
            service,
            "get_task",
            return_value=task,
        ),
        patch(
            "app.services.task.task_repository.mark_task_completed",
        ) as complete_mock,
    ):
        result = service.mark_task_completed(
            task_id=1,
            user_id=100,
        )

    assert result is task
    complete_mock.assert_not_called()


def test_reopen_todo_is_idempotent(
    service: TaskService,
) -> None:
    task = make_task(
        status=TaskStatus.TODO,
    )

    with (
        patch.object(
            service,
            "get_task",
            return_value=task,
        ),
        patch(
            "app.services.task.task_repository.reopen_task",
        ) as reopen_mock,
    ):
        result = service.reopen_task(
            task_id=1,
            user_id=100,
        )

    assert result is task
    reopen_mock.assert_not_called()


def test_reopen_in_progress_raises_conflict(
    service: TaskService,
) -> None:
    task = make_task(
        status=TaskStatus.IN_PROGRESS,
    )

    with patch.object(
        service,
        "get_task",
        return_value=task,
    ):
        with pytest.raises(
            TaskConflictError,
            match="Only completed tasks",
        ):
            service.reopen_task(
                task_id=1,
                user_id=100,
            )


def test_delete_task_success(
    service: TaskService,
) -> None:
    task = make_task()

    with (
        patch.object(
            service,
            "get_task",
            return_value=task,
        ),
        patch(
            "app.services.task.task_repository.soft_delete_task",
            return_value=task,
        ) as delete_mock,
    ):
        result = service.delete_task(
            task_id=1,
            user_id=100,
        )

    assert result is task

    delete_mock.assert_called_once_with(
        db=service.db,
        task=task,
    )


def test_create_task_rolls_back_on_database_error(
    service: TaskService,
    db: MagicMock,
) -> None:
    payload = TaskCreate(
        title="Finish project",
    )

    with (
        patch(
            "app.services.task.course_repository.get_course_by_id",
            return_value=MagicMock(),
        ),
        patch(
            "app.services.task.task_repository.create_task",
            side_effect=SQLAlchemyError("database error"),
        ),
    ):
        with pytest.raises(SQLAlchemyError):
            service.create_task(
                user_id=100,
                course_id=10,
                task_data=payload,
            )

    db.rollback.assert_called_once()

def test_update_completed_task_raises_validation(
    service: TaskService,
) -> None:
    task = make_task(
        status=TaskStatus.COMPLETED,
    )

    payload = TaskUpdate(
        title="New title",
    )

    with patch.object(
        service,
        "get_task",
        return_value=task,
    ):
        with pytest.raises(
            TaskValidationError,
        ):
            service.update_task(
                task_id=1,
                user_id=100,
                task_data=payload,
            )