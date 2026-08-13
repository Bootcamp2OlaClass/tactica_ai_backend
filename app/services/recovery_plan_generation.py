"""Recovery plan orchestration — see PHASE_10_SMART_PLANNING.md.

Deterministic first, LLM second, same philosophy as Phase 09's roadmap:
`app/services/recovery_planning.py`'s prioritization always runs and is
never blocked on LLM availability. The LLM only adds a short explanation
to the top few items on top of an order it has no ability to change --
there is no "reorder" step in the schema at all, structurally preventing
the model from doing the one thing this phase's acceptance criterion
(reproducible without the LLM) requires it not to do.

Ground-truth-filter: every task_id the model returns an explanation for
is checked against the exact set of task ids it was actually shown that
turn; anything else is dropped, never persisted or trusted.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.task import Task
from app.repositories import task_repository
from app.schemas.recovery_plan import RecoveryExplanations, RecoveryPlanItemResponse, RecoveryPlanResponse
from app.services.llm import (
    LLMExtractionError,
    LLMNotConfiguredError,
    LLMProvider,
    LLMTransientError,
    get_llm_provider,
)
from app.services.recovery_planning import PrioritizedTask, build_recovery_plan

logger = logging.getLogger(__name__)

MAX_EXPLANATIONS = 8

SYSTEM_PROMPT = """You help a university student understand a recovery \
plan that has already been deterministically prioritized from their real \
overdue and upcoming tasks -- you are not asked to prioritize or \
reorder anything, only to explain.

Below is the plan's top items, in their already-decided priority order, \
each with its task_id, urgency (overdue / due soon / due this week / \
later), whether it clusters with other deadlines, and its estimated \
effort. Use ONLY this information -- never invent a task, deadline, or \
course that isn't listed.

Rules:
- Write one short, encouraging, actionable explanation per item you \
choose to comment on (you don't have to cover every item).
- Every explanation's task_id MUST be one of the task_ids listed below. \
Never invent a task_id.
- Do not change the order or suggest a different order -- the order is \
already fixed by the student's real data, not something you control.
"""


class RecoveryPlanService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self._llm_provider = llm_provider

    def _get_llm_provider(self) -> LLMProvider:
        if self._llm_provider is not None:
            return self._llm_provider
        return get_llm_provider(self.settings)

    def build_plan(
        self, *, user_id: int, current_time: datetime | None = None
    ) -> RecoveryPlanResponse:
        now = current_time or datetime.now(timezone.utc)

        tasks: list[Task] = task_repository.list_tasks(
            self.db, user_id=user_id, limit=1000
        )
        prioritized = build_recovery_plan(tasks, current_time=now)

        explanations, unavailable_reason = self._generate_explanations(prioritized)

        items = [
            RecoveryPlanItemResponse(
                task_id=p.task.id,
                title=p.task.title,
                course_id=p.task.course_id,
                due_at=p.task.due_at,
                is_overdue=p.is_overdue,
                urgency_label=p.urgency_label,
                cluster_size=p.cluster_size,
                estimated_effort_minutes=p.estimated_effort_minutes,
                priority=p.priority,
                score=p.score,
                explanation=explanations.get(p.task.id),
            )
            for p in prioritized
        ]

        return RecoveryPlanResponse(
            generated_at=now,
            items=items,
            recommendations_unavailable_reason=unavailable_reason,
        )

    def _generate_explanations(
        self, prioritized: list[PrioritizedTask]
    ) -> tuple[dict[int, str], str | None]:
        if not prioritized:
            return {}, None

        top_items = prioritized[:MAX_EXPLANATIONS]

        try:
            provider = self._get_llm_provider()
        except LLMNotConfiguredError as exc:
            return {}, f"AI explanations are not available: {exc}"

        content = self._build_content(top_items)

        try:
            result = provider.extract_structured(
                system_prompt=SYSTEM_PROMPT,
                content=content,
                response_schema=RecoveryExplanations,
            )
        except (LLMTransientError, LLMExtractionError) as exc:
            logger.warning(
                "Recovery plan explanation generation failed, continuing "
                "with the deterministic plan only",
                extra={"error": str(exc)},
            )
            return {}, f"AI explanations could not be generated this time: {exc}"

        valid_task_ids = {p.task.id for p in top_items}
        explanations: dict[int, str] = {}
        for item in result.items:
            if item.task_id in valid_task_ids and item.task_id not in explanations:
                explanations[item.task_id] = item.explanation

        return explanations, None

    @staticmethod
    def _build_content(top_items: list[PrioritizedTask]) -> str:
        lines = []
        for p in top_items:
            due = p.task.due_at.date().isoformat() if p.task.due_at else "no due date"
            lines.append(
                f"- task_id={p.task.id}: \"{p.task.title}\" -- {p.urgency_label} "
                f"(due {due}), clusters with {p.cluster_size} other deadline(s), "
                f"~{p.estimated_effort_minutes} min estimated effort"
            )
        return "Recovery plan (already prioritized, top to bottom):\n" + "\n".join(lines)
