from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.models.task import (
    TaskPriority,
    TaskSource,
    TaskStatus,
    TaskType,
)


TASK_TITLE_MAX_LENGTH = 255


class TaskBase(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=TASK_TITLE_MAX_LENGTH,
    )

    description: str | None = None

    task_type: TaskType = TaskType.OTHER

    status: TaskStatus = TaskStatus.TODO

    priority: TaskPriority = TaskPriority.MEDIUM

    due_at: datetime | None = Field(
        default=None,
        description=(
            "Timezone-aware ISO 8601 timestamp, for example "
            "2026-08-15T17:00:00Z or "
            "2026-08-15T17:00:00+07:00."
        ),
        examples=["2026-08-15T17:00:00Z"],
    )

    estimated_minutes: int | None = Field(
        default=None,
        ge=0,
    )

    source: TaskSource = TaskSource.MANUAL

    source_document_id: int | None = Field(
        default=None,
        gt=0,
    )

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()

        return value

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()

            if not value:
                return None

        return value

    @field_validator("due_at")
    @classmethod
    def validate_due_at_timezone(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Due date must include timezone information."
            )

        return value


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=TASK_TITLE_MAX_LENGTH,
    )

    description: str | None = None

    task_type: TaskType | None = None

    status: TaskStatus | None = None

    priority: TaskPriority | None = None

    due_at: datetime | None = Field(
        default=None,
        description=(
            "Timezone-aware ISO 8601 timestamp, for example "
            "2026-08-15T17:00:00Z or "
            "2026-08-15T17:00:00+07:00."
        ),
    )

    estimated_minutes: int | None = Field(
        default=None,
        ge=0,
    )

    source: TaskSource | None = None

    source_document_id: int | None = Field(
        default=None,
        gt=0,
    )

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()

        return value

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()

            if not value:
                return None

        return value

    @field_validator("due_at")
    @classmethod
    def validate_due_at_timezone(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Due date must include timezone information."
            )

        return value


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int

    title: str
    description: str | None

    task_type: TaskType
    status: TaskStatus
    priority: TaskPriority

    due_at: datetime | None
    estimated_minutes: int | None
    completed_at: datetime | None

    source: TaskSource
    source_document_id: int | None

    is_deleted: bool
    deleted_at: datetime | None

    created_at: datetime
    updated_at: datetime

    is_overdue: bool


class TaskListResponse(BaseModel):
    items: list[TaskResponse]

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)