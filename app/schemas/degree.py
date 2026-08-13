"""Degree advisor schemas — see PHASE_11_DEGREE_ADVISOR.md.

`DegreeRecommendations` is the LLM's schema-enforced structured output
(same `LLMProvider.extract_structured` mechanism as every prior AI
feature). It can only select and briefly explain courses from the
already-computed eligible set it was given -- there is no free-text
course-name field, only `course_code`, re-verified against that exact
set before being trusted (app/services/degree_recommendation.py's
ground-truth-filter).
"""

from pydantic import BaseModel, Field


class DegreeRecommendationItem(BaseModel):
    course_code: str
    reason: str


class DegreeRecommendations(BaseModel):
    items: list[DegreeRecommendationItem] = Field(default_factory=list)


class DeclareDegreeProgramRequest(BaseModel):
    degree_program_id: int = Field(ge=1)


class EligibleCourseResponse(BaseModel):
    course_code: str
    course_name: str
    credits: int
    category: str | None


class DegreeProgressResponse(BaseModel):
    degree_program_id: int
    degree_program_name: str
    institution_name: str
    completed_credits: int
    completed_course_codes: list[str]
    unmet_requirement_count: int
    eligible_courses: list[EligibleCourseResponse]
    recommendations: list[DegreeRecommendationItem]
    recommendations_unavailable_reason: str | None
