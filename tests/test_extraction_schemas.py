import pytest
from pydantic import ValidationError

from app.schemas.extraction import (
    AcademicDocumentExtraction,
    ExtractedAssignment,
    ExtractedCourseInfo,
    ExtractedExam,
    ExtractedGradingPolicy,
    ExtractedImportantDate,
)


def test_full_extraction_payload_validates():
    extraction = AcademicDocumentExtraction.model_validate(
        {
            "course": {
                "course_name": "Intro to CS",
                "course_code": "CS101",
                "professor_name": "Dr. Smith",
                "classroom": "Room 204",
                "source_page": 1,
            },
            "assignments": [
                {"title": "Homework 1", "due_date": "2026-09-01", "source_page": 2},
            ],
            "exams": [
                {"title": "Midterm", "exam_date": "2026-10-15", "location": "Hall A", "source_page": 3},
            ],
            "important_dates": [
                {"label": "Add/drop deadline", "event_date": "2026-08-30", "source_page": 1},
            ],
            "grading_policy": {"description": "40% exams, 60% homework", "source_page": 4},
        }
    )

    assert extraction.course.course_code == "CS101"
    assert extraction.assignments[0].title == "Homework 1"
    assert extraction.exams[0].location == "Hall A"
    assert extraction.important_dates[0].label == "Add/drop deadline"
    assert extraction.grading_policy.description.startswith("40%")


def test_empty_extraction_payload_validates_with_defaults():
    extraction = AcademicDocumentExtraction.model_validate({})

    assert extraction.course is None
    assert extraction.assignments == []
    assert extraction.exams == []
    assert extraction.important_dates == []
    assert extraction.grading_policy is None


def test_assignment_requires_title():
    with pytest.raises(ValidationError):
        ExtractedAssignment.model_validate({"due_date": "2026-09-01"})


def test_exam_requires_title():
    with pytest.raises(ValidationError):
        ExtractedExam.model_validate({"exam_date": "2026-10-15"})


def test_important_date_requires_label():
    with pytest.raises(ValidationError):
        ExtractedImportantDate.model_validate({"event_date": "2026-08-30"})


def test_grading_policy_requires_description():
    with pytest.raises(ValidationError):
        ExtractedGradingPolicy.model_validate({"source_page": 1})


def test_course_info_all_fields_optional():
    course = ExtractedCourseInfo.model_validate({})
    assert course.course_name is None
    assert course.source_page is None


def test_invalid_date_format_is_rejected():
    with pytest.raises(ValidationError):
        ExtractedAssignment.model_validate({"title": "HW1", "due_date": "not-a-date"})
