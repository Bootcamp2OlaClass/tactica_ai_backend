"""Application domain exceptions."""

from app.exceptions.semester import (
    SemesterConflictError,
    SemesterError,
    SemesterNotFoundError,
    SemesterValidationError,
)

__all__ = [
    "SemesterConflictError",
    "SemesterError",
    "SemesterNotFoundError",
    "SemesterValidationError",
]
