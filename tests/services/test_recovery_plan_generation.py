"""RecoveryPlanService tests -- see PHASE_10_SMART_PLANNING.md. Grounding
(the LLM never gets to reorder or invent a task reference) and the
graceful-degradation-without-LLM path are the two properties this phase's
acceptance criteria actually require.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.task import Task, TaskStatus, TaskType
from app.schemas.recovery_plan import RecoveryExplanationItem, RecoveryExplanations
from app.services.llm import LLMNotConfiguredError, LLMTransientError
from app.services.recovery_plan_generation import RecoveryPlanService
from tests.factories import create_user_with_course

NOW = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)


class FakeLLMProvider:
    def __init__(self, result: RecoveryExplanations | None = None, error: Exception | None = None):
        self._result = result if result is not None else RecoveryExplanations(items=[])
        self._error = error
        self.calls: list[str] = []

    def extract_structured(self, *, system_prompt, content, response_schema):
        self.calls.append(content)
        if self._error is not None:
            raise self._error
        return self._result


def _add_task(db_session, *, course_id, title="Task", due_at, status=TaskStatus.TODO):
    task = Task(
        course_id=course_id, title=title, task_type=TaskType.ASSIGNMENT,
        status=status, due_at=due_at, is_deleted=False,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_build_plan_with_no_tasks_returns_an_empty_plan(db_session):
    user, course = create_user_with_course(db_session, email_prefix="recovery-empty")
    service = RecoveryPlanService(
        db=db_session, settings=SimpleNamespace(llm_provider="gemini"),
        llm_provider=FakeLLMProvider(),
    )

    plan = service.build_plan(user_id=user.id, current_time=NOW)

    assert plan.items == []
    assert plan.recommendations_unavailable_reason is None


def test_build_plan_orders_tasks_deterministically_and_attaches_explanations(db_session):
    user, course = create_user_with_course(db_session, email_prefix="recovery-basic")
    overdue = _add_task(db_session, course_id=course.id, title="Overdue essay", due_at=NOW - timedelta(days=1))
    later = _add_task(db_session, course_id=course.id, title="Later reading", due_at=NOW + timedelta(days=20))

    provider = FakeLLMProvider(
        RecoveryExplanations(
            items=[RecoveryExplanationItem(task_id=overdue.id, explanation="Do this first.")]
        )
    )
    service = RecoveryPlanService(
        db=db_session, settings=SimpleNamespace(llm_provider="gemini"), llm_provider=provider
    )

    plan = service.build_plan(user_id=user.id, current_time=NOW)

    assert [item.task_id for item in plan.items] == [overdue.id, later.id]
    assert plan.items[0].explanation == "Do this first."
    assert plan.items[1].explanation is None
    assert plan.recommendations_unavailable_reason is None


def test_build_plan_strips_a_hallucinated_task_id_from_explanations(db_session):
    user, course = create_user_with_course(db_session, email_prefix="recovery-halluc")
    real_task = _add_task(db_session, course_id=course.id, due_at=NOW - timedelta(days=1))
    fake_task_id = real_task.id + 999

    provider = FakeLLMProvider(
        RecoveryExplanations(
            items=[RecoveryExplanationItem(task_id=fake_task_id, explanation="About a task that doesn't exist.")]
        )
    )
    service = RecoveryPlanService(
        db=db_session, settings=SimpleNamespace(llm_provider="gemini"), llm_provider=provider
    )

    plan = service.build_plan(user_id=user.id, current_time=NOW)

    assert all(item.explanation is None for item in plan.items)


def test_build_plan_without_llm_provider_still_returns_the_deterministic_order(db_session, monkeypatch):
    user, course = create_user_with_course(db_session, email_prefix="recovery-no-llm")
    _add_task(db_session, course_id=course.id, due_at=NOW - timedelta(days=1))

    def _raise(settings):
        raise LLMNotConfiguredError("LLM_PROVIDER not set")

    monkeypatch.setattr("app.services.recovery_plan_generation.get_llm_provider", _raise)

    service = RecoveryPlanService(
        db=db_session, settings=SimpleNamespace(llm_provider=None), llm_provider=None
    )

    plan = service.build_plan(user_id=user.id, current_time=NOW)

    assert len(plan.items) == 1
    assert plan.items[0].explanation is None
    assert plan.recommendations_unavailable_reason is not None
    assert "not available" in plan.recommendations_unavailable_reason


def test_build_plan_handles_llm_transient_error_gracefully(db_session):
    user, course = create_user_with_course(db_session, email_prefix="recovery-transient")
    _add_task(db_session, course_id=course.id, due_at=NOW - timedelta(days=1))

    provider = FakeLLMProvider(error=LLMTransientError("rate limited"))
    service = RecoveryPlanService(
        db=db_session, settings=SimpleNamespace(llm_provider="gemini"), llm_provider=provider
    )

    plan = service.build_plan(user_id=user.id, current_time=NOW)

    assert len(plan.items) == 1
    assert plan.recommendations_unavailable_reason is not None


def test_build_plan_never_lets_the_llm_change_the_order(db_session):
    """Even though the schema has no reorder field to begin with, this
    test documents the invariant explicitly: the returned item order must
    exactly match the deterministic pipeline's own order, regardless of
    what order the fake LLM's explanations arrive in."""
    user, course = create_user_with_course(db_session, email_prefix="recovery-order")
    task_a = _add_task(db_session, course_id=course.id, title="A", due_at=NOW - timedelta(days=3))
    task_b = _add_task(db_session, course_id=course.id, title="B", due_at=NOW - timedelta(days=1))

    provider = FakeLLMProvider(
        RecoveryExplanations(
            items=[
                RecoveryExplanationItem(task_id=task_b.id, explanation="B's note"),
                RecoveryExplanationItem(task_id=task_a.id, explanation="A's note"),
            ]
        )
    )
    service = RecoveryPlanService(
        db=db_session, settings=SimpleNamespace(llm_provider="gemini"), llm_provider=provider
    )

    plan = service.build_plan(user_id=user.id, current_time=NOW)

    # Both are overdue; task_a is more overdue (3 days vs 1), so it must
    # rank first regardless of the order explanations came back in.
    assert [item.task_id for item in plan.items] == [task_a.id, task_b.id]
    assert plan.items[0].explanation == "A's note"
    assert plan.items[1].explanation == "B's note"
