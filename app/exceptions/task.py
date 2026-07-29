"""Domain exceptions raised by academic task business rules."""


class TaskError(Exception):
    """Base class for academic task domain errors."""


class TaskNotFoundError(TaskError, LookupError):
    """Raised when a task is missing or inaccessible."""


class TaskConflictError(TaskError, ValueError):
    """Raised when a task state transition conflicts with its current state."""


class TaskValidationError(TaskError, ValueError):
    """Raised when task data violates a business rule."""