from sqlalchemy.orm import Session

from app.exceptions.roadmap import RoadmapNotFoundError
from app.exceptions.semester import SemesterNotFoundError
from app.models.roadmap import SemesterRoadmap
from app.repositories.roadmap_repository import RoadmapRepository
from app.repositories.semester import SemesterRepository


class RoadmapQueryService:
    """Read-only, ownership-checked roadmap lookup -- mirrors
    ExtractionQueryService's (Phase 06) shape."""

    def __init__(
        self,
        db: Session,
        semester_repository: SemesterRepository | None = None,
        roadmap_repository: RoadmapRepository | None = None,
    ) -> None:
        self.db = db
        self.semester_repository = semester_repository or SemesterRepository(db)
        self.roadmap_repository = roadmap_repository or RoadmapRepository(db)

    def get_roadmap(self, *, semester_id: int, user_id: int) -> SemesterRoadmap:
        semester = self.semester_repository.get_by_id_and_owner(semester_id, user_id)
        if semester is None:
            raise SemesterNotFoundError("Semester not found.")

        roadmap = self.roadmap_repository.get_by_semester_id(semester_id)
        if roadmap is None:
            raise RoadmapNotFoundError(
                "No roadmap has been generated for this semester yet."
            )

        return roadmap
