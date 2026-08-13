from datetime import date

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.roadmap import (
    RoadmapGenerationStatus,
    RoadmapItem,
    RoadmapItemOrigin,
    RoadmapWeek,
    SemesterRoadmap,
)

_CLAIMABLE_STATUSES = (
    RoadmapGenerationStatus.NOT_REQUESTED,
    RoadmapGenerationStatus.QUEUED,
    RoadmapGenerationStatus.FAILED,
)


class RoadmapRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- SemesterRoadmap ---

    def get_by_semester_id(self, semester_id: int) -> SemesterRoadmap | None:
        return (
            self.db.query(SemesterRoadmap)
            .filter(SemesterRoadmap.semester_id == semester_id)
            .first()
        )

    def get_by_id(self, roadmap_id: int) -> SemesterRoadmap | None:
        return (
            self.db.query(SemesterRoadmap)
            .filter(SemesterRoadmap.id == roadmap_id)
            .first()
        )

    def get_or_create(self, semester_id: int) -> SemesterRoadmap:
        roadmap = self.get_by_semester_id(semester_id)
        if roadmap is not None:
            return roadmap

        roadmap = SemesterRoadmap(semester_id=semester_id)
        self.db.add(roadmap)
        self.db.commit()
        self.db.refresh(roadmap)
        return roadmap

    def mark_queued(self, roadmap: SemesterRoadmap) -> SemesterRoadmap:
        roadmap.status = RoadmapGenerationStatus.QUEUED
        self.db.commit()
        self.db.refresh(roadmap)
        return roadmap

    def try_start_generation(self, roadmap_id: int) -> bool:
        """Atomic UPDATE...WHERE claim -- same shape as
        DocumentRepository.try_start_chunk_embedding (Phase 07) /
        try_start_extraction (Phase 06) / try_start_processing (Phase 05).
        """
        result = self.db.execute(
            update(SemesterRoadmap)
            .where(
                SemesterRoadmap.id == roadmap_id,
                SemesterRoadmap.status.in_(_CLAIMABLE_STATUSES),
            )
            .values(status=RoadmapGenerationStatus.PROCESSING, generation_error=None)
        )
        self.db.commit()
        return result.rowcount == 1

    def mark_completed(
        self,
        roadmap: SemesterRoadmap,
        *,
        recommendations_unavailable_reason: str | None,
        generated_at,
    ) -> SemesterRoadmap:
        roadmap.status = RoadmapGenerationStatus.COMPLETED
        roadmap.generation_error = None
        roadmap.recommendations_unavailable_reason = recommendations_unavailable_reason
        roadmap.generated_at = generated_at
        roadmap.version += 1
        self.db.commit()
        self.db.refresh(roadmap)
        return roadmap

    def mark_failed(self, roadmap: SemesterRoadmap, error_message: str) -> SemesterRoadmap:
        roadmap.status = RoadmapGenerationStatus.FAILED
        roadmap.generation_error = error_message
        self.db.commit()
        self.db.refresh(roadmap)
        return roadmap

    # --- RoadmapWeek ---

    def get_or_create_week(
        self,
        *,
        roadmap_id: int,
        week_number: int,
        start_date: date,
        end_date: date,
    ) -> RoadmapWeek:
        week = (
            self.db.query(RoadmapWeek)
            .filter(
                RoadmapWeek.roadmap_id == roadmap_id,
                RoadmapWeek.week_number == week_number,
            )
            .first()
        )
        if week is not None:
            week.start_date = start_date
            week.end_date = end_date
            self.db.flush()
            return week

        week = RoadmapWeek(
            roadmap_id=roadmap_id,
            week_number=week_number,
            start_date=start_date,
            end_date=end_date,
        )
        self.db.add(week)
        self.db.flush()
        return week

    # --- RoadmapItem ---

    def list_items_by_roadmap(self, roadmap_id: int) -> list[RoadmapItem]:
        return (
            self.db.query(RoadmapItem)
            .filter(RoadmapItem.roadmap_id == roadmap_id)
            .all()
        )

    def get_deterministic_item_by_task(
        self, *, roadmap_id: int, task_id: int
    ) -> RoadmapItem | None:
        return (
            self.db.query(RoadmapItem)
            .filter(
                RoadmapItem.roadmap_id == roadmap_id,
                RoadmapItem.task_id == task_id,
                RoadmapItem.origin == RoadmapItemOrigin.DETERMINISTIC,
            )
            .first()
        )

    def upsert_deterministic_item(self, item: RoadmapItem) -> RoadmapItem:
        """`item` is either a freshly-constructed RoadmapItem (create) or
        an existing one with fields already mutated on it by the caller
        (update) -- either way this just adds-if-new and flushes. Never
        called for an item with is_user_edited=True; the generation
        service is responsible for that check (see roadmap_generation.py)
        so this repository stays a plain persistence layer, not a policy
        holder."""
        if item.id is None:
            self.db.add(item)
        self.db.flush()
        return item

    def delete_deterministic_items_not_in(
        self, *, roadmap_id: int, keep_task_ids: set[int]
    ) -> None:
        """Removes deterministic items whose source task no longer
        qualifies for the roadmap (deleted, completed, or its due date no
        longer falls in-range) -- except any the student has edited,
        which are preserved even if now "stale" relative to the task
        (see PHASE_09_SEMESTER_ROADMAP.md's edit-preservation rule)."""
        query = self.db.query(RoadmapItem).filter(
            RoadmapItem.roadmap_id == roadmap_id,
            RoadmapItem.origin == RoadmapItemOrigin.DETERMINISTIC,
            RoadmapItem.is_user_edited.is_(False),
        )
        if keep_task_ids:
            query = query.filter(RoadmapItem.task_id.notin_(keep_task_ids))
        query.delete(synchronize_session=False)
        self.db.flush()

    def replace_recommendation_items(
        self, *, roadmap_id: int, new_items: list[RoadmapItem]
    ) -> list[RoadmapItem]:
        """Deletes every non-edited RECOMMENDATION item for this roadmap,
        then inserts the freshly-generated set -- recommendations carry no
        review state to preserve across a regenerate (unlike Phase 06's
        ExtractionCandidate), except the one thing that always survives
        regardless of item type: is_user_edited=True."""
        self.db.query(RoadmapItem).filter(
            RoadmapItem.roadmap_id == roadmap_id,
            RoadmapItem.origin == RoadmapItemOrigin.AI_GENERATED,
            RoadmapItem.is_user_edited.is_(False),
        ).delete(synchronize_session=False)

        self.db.add_all(new_items)
        self.db.flush()
        return new_items

    def get_item_owned(self, *, item_id: int, user_id: int) -> RoadmapItem | None:
        """Ownership chain: RoadmapItem -> RoadmapWeek -> SemesterRoadmap
        -> Semester.user_id. A plain join, not a denormalized user_id
        column -- this domain's query volume/security-criticality doesn't
        warrant Phase 07's DocumentChunk-style denormalization (see
        app/models/roadmap.py's module docstring)."""
        from app.models.semester import Semester

        return (
            self.db.query(RoadmapItem)
            .join(RoadmapWeek, RoadmapItem.week_id == RoadmapWeek.id)
            .join(SemesterRoadmap, RoadmapWeek.roadmap_id == SemesterRoadmap.id)
            .join(Semester, SemesterRoadmap.semester_id == Semester.id)
            .filter(RoadmapItem.id == item_id, Semester.user_id == user_id)
            .first()
        )

    def update_item(
        self, item: RoadmapItem, *, title: str | None, description: str | None
    ) -> RoadmapItem:
        if title is not None:
            item.title = title
        if description is not None:
            item.description = description
        item.is_user_edited = True
        self.db.commit()
        self.db.refresh(item)
        return item
