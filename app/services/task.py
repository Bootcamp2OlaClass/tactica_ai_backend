import logging
from datetime import datetime, timezone
from math import ceil
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.exceptions.task import (
    TaskConflictError,
    TaskNotFoundError,
    TaskValidationError,
)
from app.models.course import Course
from app.models.task import (
    Task,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from app.repositories import course_repository
from app.repositories import task_repository
from app.schemas.task import TaskCreate, TaskUpdate

if TYPE_CHECKING:
    from app.services.calendar_sync import CalendarSyncService

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(
        self,
        db: Session,
        calendar_sync_service: "CalendarSyncService | None" = None,
    ) -> None:
        self.db = db
        # Optional (Phase 12) -- defaults to None so every existing
        # TaskService(db) call site and test, across every prior phase,
        # is completely unaffected. Only wired to a real
        # CalendarSyncService at the router dependency level.
        self.calendar_sync_service = calendar_sync_service

    def _get_owned_course(
        self,
        course_id: int,
        user_id: int,
    ) -> Course:
        course = course_repository.get_course_by_id(
            db=self.db,
            course_id=course_id,
            user_id=user_id,
        )

        if course is None:
            raise TaskNotFoundError("Course not found.")

        return course

    def create_task(
        self,
        user_id: int,
        course_id: int,
        task_data: TaskCreate,
    ) -> Task:
        self._get_owned_course(
            course_id=course_id,
            user_id=user_id,
        )

        if task_data.status == TaskStatus.COMPLETED:
            raise TaskValidationError(
                "Use the complete operation to mark a task as completed."
            )

        task_payload = task_data.model_dump()
        task_payload["course_id"] = course_id

        try:
            return task_repository.create_task(
                db=self.db,
                task_data=task_payload,
            )

        except SQLAlchemyError:
            self.db.rollback()
            raise

    def get_task(
        self,
        task_id: int,
        user_id: int,
    ) -> Task:
        task = task_repository.get_task_by_id(
            db=self.db,
            task_id=task_id,
            user_id=user_id,
        )

        if task is None:
            raise TaskNotFoundError("Task not found.")

        return task

    def list_tasks(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        course_id: int | None = None,
        semester_id: int | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        task_type: TaskType | None = None,
        due_from: datetime | None = None,
        due_to: datetime |None = None,
        overdue: bool | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict[str, object]:
        if page < 1:
            raise TaskValidationError(
                "Page must be greater than or equal to 1."
            )

        if page_size < 1:
            raise TaskValidationError(
                "Page size must be greater than or equal to 1."
            )

        if due_from is not None and due_to is not None:
            if due_from > due_to:
                raise TaskValidationError(
                    "Due-from must be earlier than or equal to due-to."
                )

        if course_id is not None:
            self._get_owned_course(
                course_id=course_id,
                user_id=user_id,
            )

        offset = (page - 1) * page_size

        current_time = (
            datetime.now(timezone.utc)
            if overdue is not None
            else None
        )

        items = task_repository.list_tasks(
            db=self.db,
            user_id=user_id,
            offset=offset,
            limit=page_size,
            course_id=course_id,
            semester_id=semester_id,
            status=status,
            priority=priority,
            task_type=task_type,
            due_from=due_from,
            due_to=due_to,
            overdue=overdue,
            current_time=current_time,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total = task_repository.count_tasks(
            db=self.db,
            user_id=user_id,
            course_id=course_id,
            semester_id=semester_id,
            status=status,
            priority=priority,
            task_type=task_type,
            due_from=due_from,
            due_to=due_to,
            overdue=overdue,
            current_time=current_time,
            search=search,
        )

        total_pages = (
            ceil(total / page_size)
            if total > 0
            else 0
        )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def update_task(
        self,
        task_id: int,
        user_id: int,
        task_data: TaskUpdate,
    ) -> Task:
        task = self.get_task(
            task_id=task_id,
            user_id=user_id,
        )

        update_data = task_data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            return task

        if task.status == TaskStatus.COMPLETED:
            raise TaskValidationError(
                "Use the reopen operation before updating a completed task."
            )

        if "status" in update_data:
            new_status = update_data["status"]

            if new_status == TaskStatus.COMPLETED:
                raise TaskValidationError(
                    "Use the complete operation to mark a task as completed."
                )

        try:
            return task_repository.update_task(
                db=self.db,
                task=task,
                update_data=update_data,
            )

        except SQLAlchemyError:
            self.db.rollback()
            raise

    def mark_task_completed(
        self,
        task_id: int,
        user_id: int,
    ) -> Task:
        task = self.get_task(
            task_id=task_id,
            user_id=user_id,
        )

        if task.status == TaskStatus.COMPLETED:
            return task

        if task.status == TaskStatus.CANCELLED:
            raise TaskConflictError(
                "A cancelled task cannot be marked as completed."
            )

        try:
            return task_repository.mark_task_completed(
                db=self.db,
                task=task,
                completed_at=datetime.now(timezone.utc),
            )

        except SQLAlchemyError:
            self.db.rollback()
            raise

    def reopen_task(
        self,
        task_id: int,
        user_id: int,
    ) -> Task:
        task = self.get_task(
            task_id=task_id,
            user_id=user_id,
        )

        if task.status == TaskStatus.TODO:
            return task

        if task.status != TaskStatus.COMPLETED:
            raise TaskConflictError(
                "Only completed tasks can be reopened."
            )

        try:
            return task_repository.reopen_task(
                db=self.db,
                task=task,
            )

        except SQLAlchemyError:
            self.db.rollback()
            raise

    def delete_task(
        self,
        task_id: int,
        user_id: int,
    ) -> Task:
        task = self.get_task(
            task_id=task_id,
            user_id=user_id,
        )

        try:
            deleted = task_repository.soft_delete_task(
                db=self.db,
                task=task,
            )

        except SQLAlchemyError:
            self.db.rollback()
            raise

        if self.calendar_sync_service is not None:
            # Non-fatal on failure, same reasoning as Phase 03's
            # DocumentDeleteService cleaning up the extracted-content
            # artifact: the task deletion itself already succeeded by
            # this point, and a calendar-side error (network, expired
            # token, event already gone) shouldn't turn a successful
            # delete into a user-visible failure.
            try:
                self.calendar_sync_service.unsync_task(task=deleted, user_id=user_id)
            except Exception:
                logger.exception(
                    "Failed to remove calendar event for deleted task",
                    extra={"task_id": task_id, "user_id": user_id},
                )

        return deleted