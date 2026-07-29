"""Application domain exceptions."""

from app.exceptions.course import (
    CourseConflictError,
    CourseError,
    CourseNotFoundError,
    CourseValidationError,
)

from app.exceptions.semester import (
    SemesterConflictError,
    SemesterError,
    SemesterNotFoundError,
    SemesterValidationError,
)

from app.exceptions.task import (
    TaskConflictError,
    TaskError,
    TaskNotFoundError,
    TaskValidationError,
)


__all__ = [
    "CourseConflictError",
    "CourseError",
    "CourseNotFoundError",
    "CourseValidationError",

    "SemesterConflictError",
    "SemesterError",
    "SemesterNotFoundError",
    "SemesterValidationError",

    "TaskConflictError",
    "TaskError",
    "TaskNotFoundError",
    "TaskValidationError",
]