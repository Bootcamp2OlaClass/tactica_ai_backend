"""Recovery plan schemas — see PHASE_10_SMART_PLANNING.md.

`RecoveryExplanations` is the LLM's schema-enforced structured output
(same `LLMProvider.extract_structured` mechanism as Phase 06/08/09) for
the optional explanation layer -- it never reorders anything, only adds
a short natural-language note to items the deterministic pipeline (see
app/services/recovery_planning.py) already ranked. `task_id` is
re-verified against the real tasks shown that turn before being trusted
(app/services/recovery_plan_generation.py's ground-truth-filter).
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.task import TaskPriority


class RecoveryExplanationItem(BaseModel):
    task_id: int
    explanation: str


class RecoveryExplanations(BaseModel):
    items: list[RecoveryExplanationItem] = Field(default_factory=list)


class RecoveryPlanItemResponse(BaseModel):
    task_id: int
    title: str
    course_id: int
    due_at: datetime | None
    is_overdue: bool
    urgency_label: str
    cluster_size: int
    estimated_effort_minutes: int
    priority: TaskPriority
    score: float
    explanation: str | None


class RecoveryPlanResponse(BaseModel):
    generated_at: datetime
    items: list[RecoveryPlanItemResponse]
    recommendations_unavailable_reason: str | None
