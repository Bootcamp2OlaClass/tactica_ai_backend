from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import ProcessingStatus
from app.models.task import TaskPriority, TaskStatus, TaskType
from app.schemas.semester import SemesterResponse


class DashboardDeadlineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    title: str
    task_type: TaskType
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime


class DashboardDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    file_name: str
    status: ProcessingStatus
    created_at: datetime


class DashboardSummaryResponse(BaseModel):
    """Complete payload consumed by the frontend dashboard."""

    current_semester: SemesterResponse | None
    active_course_count: int = Field(ge=0)
    incomplete_task_count: int = Field(ge=0)
    overdue_task_count: int = Field(ge=0)
    tasks_due_within_seven_days_count: int = Field(ge=0)
    upcoming_deadlines: list[DashboardDeadlineResponse]
    recent_documents: list[DashboardDocumentResponse]
