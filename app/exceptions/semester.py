"""Domain exceptions raised by semester business rules."""


class SemesterError(Exception):
    """Base class for semester domain errors."""


class SemesterNotFoundError(SemesterError, LookupError):
    """Raised when a semester is missing or inaccessible."""


class SemesterConflictError(SemesterError, ValueError):
    """Raised when a semester conflicts with an existing semester."""


class SemesterValidationError(SemesterError, ValueError):
    """Raised when semester data violates a business rule."""
