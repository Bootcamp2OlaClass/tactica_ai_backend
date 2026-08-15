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
    # The Document ORM model (app/models/document.py) names these
    # original_file_name/processing_status -- DocumentResponse (Phase 03,
    # app/schemas/document.py) exposes them under those same names, but this
    # dashboard summary was written against shorter field names the frontend
    # already consumes (types/dashboard.ts, lib/mappers/dashboard.ts). A
    # bare `from_attributes=True` needs an exact attribute-name match, so
    # without validation_alias every /api/v1/dashboard call with at least
    # one document 500s with a Pydantic "field required" error instead of
    # ever reaching a client. Aliasing here keeps the established
    # file_name/status wire contract instead of changing it to match the
    # model (which would also require updating the frontend mapper).
    file_name: str = Field(validation_alias="original_file_name")
    status: ProcessingStatus = Field(validation_alias="processing_status")
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
