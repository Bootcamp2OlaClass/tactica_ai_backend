"""Roadmap generation task — see PHASE_09_SEMESTER_ROADMAP.md.

Mirrors app/worker/tasks/rag.py's (Phase 07) idempotency design exactly:
an atomic UPDATE...WHERE claim (RoadmapRepository.try_start_generation),
retries skip the claim (self.request.retries == 0 gate), and a custom
Task.on_failure marks the roadmap FAILED exactly once if retries are
ultimately exhausted.

Unlike Phase 06/07's tasks, this one has no autoretry_for -- LLM
transient/permanent failures never reach this task at all, since
RoadmapGenerationService.generate() catches them internally and degrades
to `recommendations_unavailable_reason` rather than raising (deterministic
items are never blocked on LLM availability). Anything that does escape
generate() is a genuine unexpected failure (e.g. a database error), which
should fail the task immediately and mark the roadmap FAILED via
on_failure -- not be silently retried against the same likely-persistent
cause.
"""

from celery.utils.log import get_task_logger
from celery import Task

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.roadmap import RoadmapGenerationStatus
from app.models.semester import Semester
from app.repositories.roadmap_repository import RoadmapRepository
from app.services.roadmap_generation import RoadmapGenerationService
from app.worker.celery_app import AI_QUEUE, celery_app

logger = get_task_logger(__name__)
settings = get_settings()


class RoadmapGenerationTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        roadmap_id = args[0] if args else kwargs.get("roadmap_id")
        if roadmap_id is None:
            return

        db = SessionLocal()
        try:
            repository = RoadmapRepository(db)
            roadmap = repository.get_by_id(roadmap_id)
            if (
                roadmap is not None
                and roadmap.status == RoadmapGenerationStatus.PROCESSING
            ):
                repository.mark_failed(
                    roadmap, "Roadmap generation failed unexpectedly."
                )
        finally:
            db.close()


@celery_app.task(
    name="ai.generate_roadmap",
    bind=True,
    base=RoadmapGenerationTask,
    queue=AI_QUEUE,
)
def generate_roadmap(self, roadmap_id: int) -> dict:
    db = SessionLocal()
    try:
        repository = RoadmapRepository(db)

        if self.request.retries == 0:
            claimed = repository.try_start_generation(roadmap_id)
            if not claimed:
                roadmap = repository.get_by_id(roadmap_id)
                if roadmap is None:
                    logger.info(
                        "generate_roadmap: roadmap not found, skipping",
                        extra={"roadmap_id": roadmap_id},
                    )
                    return {"status": "skipped", "reason": "not_found"}
                logger.info(
                    "generate_roadmap: not claimable, skipping",
                    extra={"roadmap_id": roadmap_id, "status": roadmap.status.value},
                )
                return {
                    "status": "skipped",
                    "reason": f"status_{roadmap.status.value.lower()}",
                }

        roadmap = repository.get_by_id(roadmap_id)
        if roadmap is None:
            logger.info(
                "generate_roadmap: roadmap deleted mid-flight, skipping",
                extra={"roadmap_id": roadmap_id},
            )
            return {"status": "skipped", "reason": "deleted_mid_flight"}

        semester = db.query(Semester).filter(Semester.id == roadmap.semester_id).first()
        if semester is None:
            repository.mark_failed(roadmap, "Semester no longer exists.")
            return {"status": "failed", "reason": "semester_not_found"}

        logger.info(
            "generate_roadmap: started",
            extra={"roadmap_id": roadmap_id, "attempt": self.request.retries + 1},
        )

        service = RoadmapGenerationService(db=db, settings=settings)
        roadmap = service.generate(roadmap, semester)

        logger.info(
            "generate_roadmap: completed",
            extra={
                "roadmap_id": roadmap_id,
                "version": roadmap.version,
                "recommendations_unavailable": bool(
                    roadmap.recommendations_unavailable_reason
                ),
            },
        )

        return {
            "status": "completed",
            "roadmap_id": roadmap_id,
            "version": roadmap.version,
        }
    finally:
        db.close()
