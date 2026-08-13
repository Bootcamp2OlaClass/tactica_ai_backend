"""Semester roadmap generation — see PHASE_09_SEMESTER_ROADMAP.md.

Deterministic first, LLM second (section-titled that way in the phase
brief on purpose): `app/services/roadmap_scheduling.py`'s week/item
computation always runs and always succeeds if it runs at all (it's pure
calendar/status math over the student's own Task rows) -- roadmap
generation is never blocked on LLM availability. The LLM recommendation
pass is best-effort on top: if no provider is configured or the call
fails, the roadmap still completes with `recommendations_unavailable_reason`
set, not FAILED.

The recommendation pass reuses Phase 06/08's schema-enforced generation
mechanism (`LLMProvider.extract_structured`) and a ground-truth-filter
identical in spirit to Phase 08's citation check: every `related_task_id`
the model proposes is re-verified against the real tasks it was actually
given this turn before being trusted; an invalid reference is stripped,
never invented data passed through.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.roadmap import RoadmapItem, RoadmapItemOrigin, RoadmapItemType, SemesterRoadmap
from app.models.semester import Semester
from app.repositories import task_repository
from app.repositories.roadmap_repository import RoadmapRepository
from app.schemas.roadmap import RoadmapRecommendationItem, RoadmapRecommendations
from app.services.llm import (
    LLMExtractionError,
    LLMNotConfiguredError,
    LLMProvider,
    LLMTransientError,
    get_llm_provider,
)
from app.services.roadmap_scheduling import ItemDraft, WeekDraft, compute_deterministic_items, compute_weeks

logger = logging.getLogger(__name__)

MAX_RECOMMENDATIONS_PER_GENERATION = 12

SYSTEM_PROMPT = """You help a university student prioritize their semester \
by writing a small number of short workload/prioritization recommendations \
on top of a deterministic weekly breakdown that has already been computed \
from their real courses and deadlines -- you are not asked to invent or \
recalculate any deadline yourself.

The breakdown below lists, for each week, the real assignments/exams \
already scheduled (each with a task_id). Use ONLY these -- never invent a \
course name, deadline, or task that isn't listed.

Rules:
- Write at most a small handful of recommendations total (prioritization \
advice, workload warnings for weeks with multiple deadlines, general \
preparation tips) -- quality over quantity, not one per task.
- Every recommendation's week_number MUST be one of the week numbers \
listed below.
- If a recommendation is about a specific task, set related_task_id to \
that task's exact task_id from the list. If it's general advice not tied \
to one task, leave related_task_id unset -- never invent a task_id.
- Do not restate deadlines that are already obvious from the list; add \
actual planning value (e.g. "these two are due the same week, start X \
earlier").
"""


class RoadmapGenerationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        roadmap_repository: RoadmapRepository | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.roadmap_repository = roadmap_repository or RoadmapRepository(db)
        self._llm_provider = llm_provider

    def generate(self, roadmap: SemesterRoadmap, semester: Semester) -> SemesterRoadmap:
        weeks = compute_weeks(semester_start=semester.start_date, semester_end=semester.end_date)
        tasks = task_repository.list_tasks(
            self.db, user_id=semester.user_id, semester_id=semester.id, limit=1000
        )

        item_drafts = compute_deterministic_items(weeks=weeks, tasks=tasks)
        week_id_by_number = self._persist_deterministic_items(
            roadmap, weeks=weeks, item_drafts=item_drafts
        )

        recommendations_unavailable_reason = self._generate_and_persist_recommendations(
            roadmap, weeks=weeks, item_drafts=item_drafts, week_id_by_number=week_id_by_number
        )

        return self.roadmap_repository.mark_completed(
            roadmap,
            recommendations_unavailable_reason=recommendations_unavailable_reason,
            generated_at=datetime.now(timezone.utc),
        )

    # --- Deterministic pass ---

    def _persist_deterministic_items(
        self,
        roadmap: SemesterRoadmap,
        *,
        weeks: list[WeekDraft],
        item_drafts: list[ItemDraft],
    ) -> dict[int, int]:
        week_id_by_number = {
            week.week_number: self.roadmap_repository.get_or_create_week(
                roadmap_id=roadmap.id,
                week_number=week.week_number,
                start_date=week.start_date,
                end_date=week.end_date,
            ).id
            for week in weeks
        }

        kept_task_ids: set[int] = set()

        for draft in item_drafts:
            existing = self.roadmap_repository.get_deterministic_item_by_task(
                roadmap_id=roadmap.id, task_id=draft.task_id
            )

            if existing is not None:
                kept_task_ids.add(draft.task_id)
                if existing.is_user_edited:
                    # The student customized this item -- regeneration
                    # must never silently overwrite it, even if the
                    # underlying task's due date/type has since changed.
                    continue
                existing.week_id = week_id_by_number[draft.week_number]
                existing.item_type = draft.item_type
                existing.title = draft.title
                existing.course_id = draft.course_id
                existing.due_date = draft.due_date
                self.roadmap_repository.upsert_deterministic_item(existing)
                continue

            new_item = RoadmapItem(
                week_id=week_id_by_number[draft.week_number],
                roadmap_id=roadmap.id,
                item_type=draft.item_type,
                origin=RoadmapItemOrigin.DETERMINISTIC,
                title=draft.title,
                task_id=draft.task_id,
                course_id=draft.course_id,
                due_date=draft.due_date,
            )
            self.roadmap_repository.upsert_deterministic_item(new_item)
            kept_task_ids.add(draft.task_id)

        self.roadmap_repository.delete_deterministic_items_not_in(
            roadmap_id=roadmap.id, keep_task_ids=kept_task_ids
        )
        self.db.commit()
        return week_id_by_number

    # --- LLM recommendation pass (best-effort) ---

    def _get_llm_provider(self) -> LLMProvider:
        if self._llm_provider is not None:
            return self._llm_provider
        return get_llm_provider(self.settings)

    def _generate_and_persist_recommendations(
        self,
        roadmap: SemesterRoadmap,
        *,
        weeks: list[WeekDraft],
        item_drafts: list[ItemDraft],
        week_id_by_number: dict[int, int],
    ) -> str | None:
        if not weeks:
            return "The semester has no valid week range to generate recommendations for."

        try:
            provider = self._get_llm_provider()
        except LLMNotConfiguredError as exc:
            return f"AI recommendations are not available: {exc}"

        content = self._build_content(weeks=weeks, item_drafts=item_drafts)

        try:
            result = provider.extract_structured(
                system_prompt=SYSTEM_PROMPT,
                content=content,
                response_schema=RoadmapRecommendations,
            )
        except (LLMTransientError, LLMExtractionError) as exc:
            logger.warning(
                "Roadmap recommendation generation failed, continuing with "
                "deterministic items only",
                extra={"roadmap_id": roadmap.id, "error": str(exc)},
            )
            return f"AI recommendations could not be generated this time: {exc}"

        filtered = self._ground_truth_filter(result.items, weeks=weeks, item_drafts=item_drafts)

        task_course_by_id = {draft.task_id: draft.course_id for draft in item_drafts}

        new_items = [
            RoadmapItem(
                week_id=week_id_by_number[rec.week_number],
                roadmap_id=roadmap.id,
                item_type=RoadmapItemType.RECOMMENDATION,
                origin=RoadmapItemOrigin.AI_GENERATED,
                title=rec.title,
                description=rec.description,
                task_id=rec.related_task_id,
                course_id=task_course_by_id.get(rec.related_task_id),
                due_date=None,
            )
            for rec in filtered
        ]
        self.roadmap_repository.replace_recommendation_items(
            roadmap_id=roadmap.id, new_items=new_items
        )
        self.db.commit()
        return None

    @staticmethod
    def _build_content(*, weeks: list[WeekDraft], item_drafts: list[ItemDraft]) -> str:
        items_by_week: dict[int, list[ItemDraft]] = {week.week_number: [] for week in weeks}
        for draft in item_drafts:
            items_by_week[draft.week_number].append(draft)

        sections = []
        for week in weeks:
            drafts = items_by_week[week.week_number]
            if drafts:
                lines = "\n".join(
                    f"  - task_id={d.task_id}: {d.title} (due {d.due_date.isoformat()})"
                    for d in drafts
                )
            else:
                lines = "  (nothing scheduled)"
            sections.append(
                f"Week {week.week_number} ({week.start_date.isoformat()} to "
                f"{week.end_date.isoformat()}):\n{lines}"
            )

        return "\n\n".join(sections)

    @staticmethod
    def _ground_truth_filter(
        recommendations: list[RoadmapRecommendationItem],
        *,
        weeks: list[WeekDraft],
        item_drafts: list[ItemDraft],
    ) -> list[RoadmapRecommendationItem]:
        valid_week_numbers = {week.week_number for week in weeks}
        valid_task_ids = {draft.task_id for draft in item_drafts}

        filtered: list[RoadmapRecommendationItem] = []
        for rec in recommendations[:MAX_RECOMMENDATIONS_PER_GENERATION]:
            if rec.week_number not in valid_week_numbers:
                # Can't be placed anywhere trustworthy -- drop entirely,
                # never guess which week was "meant."
                continue

            related_task_id = rec.related_task_id
            if related_task_id is not None and related_task_id not in valid_task_ids:
                # A task_id that was never actually given to the model --
                # keep the recommendation text, strip the fabricated
                # reference. System data wins over the model's claim.
                related_task_id = None

            filtered.append(
                RoadmapRecommendationItem(
                    week_number=rec.week_number,
                    title=rec.title,
                    description=rec.description,
                    related_task_id=related_task_id,
                )
            )

        return filtered
