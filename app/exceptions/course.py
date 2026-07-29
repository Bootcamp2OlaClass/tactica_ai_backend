"""Domain exceptions raised by course business rules."""


class CourseError(Exception):
    """Base class for course domain errors."""


class CourseNotFoundError(CourseError, LookupError):
    """Raised when a course is missing or inaccessible."""


class CourseConflictError(CourseError, ValueError):
    """Raised when a course conflicts with an existing course."""


class CourseValidationError(CourseError, ValueError):
    """Raised when course data violates a business rule."""