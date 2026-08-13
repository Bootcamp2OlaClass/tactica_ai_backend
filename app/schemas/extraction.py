"""Structured extraction target schemas — see ADR-006, Phase 06.

Minimum viable set: only fields the product actually has a place for
(Course.instructor_name/classroom, Task title/due_at) get a real accept
side-effect (app/services/document_extraction.py). Everything else is
review-only for now — not over-modeled ahead of real accuracy data, per
the phase brief.

Every entity carries `source_page`, tracing back to Phase 05's page-level
extracted-content artifact -- provenance is never lost.
"""

from datetime import date

from pydantic import BaseModel, Field


class ExtractedCourseInfo(BaseModel):
    course_name: str | None = None
    course_code: str | None = None
    professor_name: str | None = None
    classroom: str | None = None
    source_page: int | None = None


class ExtractedAssignment(BaseModel):
    title: str
    due_date: date | None = None
    description: str | None = None
    source_page: int | None = None


class ExtractedExam(BaseModel):
    title: str
    exam_date: date | None = None
    location: str | None = None
    source_page: int | None = None


class ExtractedImportantDate(BaseModel):
    label: str
    event_date: date | None = None
    source_page: int | None = None


class ExtractedGradingPolicy(BaseModel):
    description: str
    source_page: int | None = None


class AcademicDocumentExtraction(BaseModel):
    """The full structured-output schema the LLM must conform to —
    enforced by the provider's own structured-output mode, not by asking
    nicely (see app/services/llm/base.py)."""

    course: ExtractedCourseInfo | None = None
    assignments: list[ExtractedAssignment] = Field(default_factory=list)
    exams: list[ExtractedExam] = Field(default_factory=list)
    important_dates: list[ExtractedImportantDate] = Field(default_factory=list)
    grading_policy: ExtractedGradingPolicy | None = None
