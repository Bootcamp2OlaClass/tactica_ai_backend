"""Roadmap schemas — see PHASE_09_SEMESTER_ROADMAP.md.

`RoadmapRecommendations` is the LLM's schema-enforced structured output
(same `LLMProvider.extract_structured` mechanism as Phase 06/08) for the
Generate step of the AI-recommendation pass -- deliberately the *only*
LLM-facing schema in this phase; deterministic items (see
app/services/roadmap_scheduling.py) never go through the model at all.
`related_task_id` is re-verified against the student's real tasks before
being trusted (the ground-truth-filter step in
app/services/roadmap_generation.py) -- never taken at face value.

The remaining classes are the public API request/response shapes.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.roadmap import (
    RoadmapGenerationStatus,
    RoadmapItemOrigin,
    RoadmapItemType,
)


class RoadmapRecommendationItem(BaseModel):
    week_number: int
    title: str
    description: str
    related_task_id: int | None = None


class RoadmapRecommendations(BaseModel):
    items: list[RoadmapRecommendationItem] = Field(default_factory=list)


class RoadmapGenerateRequest(BaseModel):
    pass


class RoadmapItemUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class RoadmapItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    week_id: int
    item_type: RoadmapItemType
    origin: RoadmapItemOrigin
    title: str
    description: str | None
    task_id: int | None
    course_id: int | None
    due_date: date | None
    is_user_edited: bool
    created_at: datetime
    updated_at: datetime


class RoadmapWeekResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    week_number: int
    start_date: date
    end_date: date
    items: list[RoadmapItemResponse]


class RoadmapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    semester_id: int
    status: RoadmapGenerationStatus
    version: int
    generated_at: datetime | None
    generation_error: str | None
    recommendations_unavailable_reason: str | None
    weeks: list[RoadmapWeekResponse]
