import logging

from sqlalchemy.orm import Session

from app.exceptions.roadmap import (
    RoadmapGenerationAlreadyInProgressError,
    RoadmapQueueUnavailableError,
)
from app.exceptions.semester import SemesterNotFoundError
from app.models.roadmap import RoadmapGenerationStatus, SemesterRoadmap
from app.repositories.roadmap_repository import RoadmapRepository
from app.repositories.semester import SemesterRepository
from app.worker.tasks.roadmap import generate_roadmap

logger = logging.getLogger(__name__)

_ALREADY_RUNNING_STATUSES = (
    RoadmapGenerationStatus.QUEUED,
    RoadmapGenerationStatus.PROCESSING,
)


class RoadmapGenerationTriggerService:
    """Validates ownership/readiness and enqueues the Phase 09 roadmap
    generation task -- same check-then-enqueue-then-mark_queued shape as
    DocumentEmbeddingTriggerService (Phase 07) / DocumentExtractionTriggerService
    (Phase 06). The atomic claim (try_start_generation) happens inside the
    task at run time, not here -- same split as every prior phase's
    trigger service."""

    def __init__(
        self,
        db: Session,
        semester_repository: SemesterRepository | None = None,
        roadmap_repository: RoadmapRepository | None = None,
    ) -> None:
        self.db = db
        self.semester_repository = semester_repository or SemesterRepository(db)
        self.roadmap_repository = roadmap_repository or RoadmapRepository(db)

    def trigger_generation(self, *, semester_id: int, user_id: int) -> SemesterRoadmap:
        semester = self.semester_repository.get_by_id_and_owner(semester_id, user_id)
        if semester is None:
            raise SemesterNotFoundError("Semester not found.")

        roadmap = self.roadmap_repository.get_or_create(semester_id)

        if roadmap.status in _ALREADY_RUNNING_STATUSES:
            raise RoadmapGenerationAlreadyInProgressError(
                f"Roadmap generation is already {roadmap.status.value.lower()}."
            )

        try:
            generate_roadmap.delay(roadmap.id)
        except Exception as error:
            logger.exception(
                "Failed to enqueue roadmap generation",
                extra={"roadmap_id": roadmap.id, "semester_id": semester_id},
            )
            raise RoadmapQueueUnavailableError(
                "Unable to queue roadmap generation right now. Please try again shortly."
            ) from error

        return self.roadmap_repository.mark_queued(roadmap)
