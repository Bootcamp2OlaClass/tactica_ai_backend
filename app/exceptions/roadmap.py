class RoadmapError(Exception):
    """Base exception for semester roadmap operations."""


class RoadmapGenerationAlreadyInProgressError(RoadmapError):
    """Raised when /generate is triggered while the roadmap's current
    status doesn't allow (re-)triggering (already QUEUED/PROCESSING)."""


class RoadmapQueueUnavailableError(RoadmapError):
    """Raised when the generation task can't be enqueued (e.g. Celery/
    Redis unreachable at trigger time) -- distinct from an LLM-provider
    problem, which never blocks generation at all (see
    app/services/roadmap_generation.py's deterministic-first design)."""


class RoadmapNotFoundError(RoadmapError):
    """Raised when a semester has no roadmap yet, or it isn't owned by the
    requesting user."""


class RoadmapItemNotFoundError(RoadmapError):
    """Raised when a roadmap item doesn't exist or isn't owned (via its
    week -> roadmap -> semester chain) by the requesting user."""
