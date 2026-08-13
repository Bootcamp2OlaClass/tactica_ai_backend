"""Pure unit tests for the deterministic recovery-plan pipeline -- see
PHASE_10_SMART_PLANNING.md's acceptance criterion: prioritization order
must be reproducible without the LLM. No database, no LLM, anywhere in
this file.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.task import TaskPriority, TaskStatus, TaskType
from app.services.recovery_planning import build_recovery_plan

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def _task(**overrides):
    defaults = dict(
        id=1,
        course_id=10,
        title="Untitled",
        task_type=TaskType.ASSIGNMENT,
        status=TaskStatus.TODO,
        due_at=None,
        estimated_minutes=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_build_recovery_plan_is_reproducible_across_calls():
    tasks = [
        _task(id=1, due_at=NOW - timedelta(days=2)),
        _task(id=2, due_at=NOW + timedelta(hours=5)),
        _task(id=3, due_at=NOW + timedelta(days=10)),
    ]

    first = [p.task.id for p in build_recovery_plan(tasks, current_time=NOW)]
    second = [p.task.id for p in build_recovery_plan(tasks, current_time=NOW)]

    assert first == second


def test_overdue_tasks_rank_above_everything_else():
    tasks = [
        _task(id=1, title="Not due yet", due_at=NOW + timedelta(days=1)),
        _task(id=2, title="Overdue", due_at=NOW - timedelta(hours=1)),
    ]

    plan = build_recovery_plan(tasks, current_time=NOW)

    assert plan[0].task.id == 2
    assert plan[0].is_overdue is True
    assert plan[0].urgency_label == "overdue"
    assert plan[1].is_overdue is False


def test_excludes_completed_and_cancelled_tasks():
    tasks = [
        _task(id=1, status=TaskStatus.TODO, due_at=NOW - timedelta(days=1)),
        _task(id=2, status=TaskStatus.COMPLETED, due_at=NOW - timedelta(days=5)),
        _task(id=3, status=TaskStatus.CANCELLED, due_at=NOW - timedelta(days=5)),
        _task(id=4, status=TaskStatus.IN_PROGRESS, due_at=NOW + timedelta(hours=2)),
    ]

    plan = build_recovery_plan(tasks, current_time=NOW)

    assert {p.task.id for p in plan} == {1, 4}


def test_tasks_with_no_due_date_are_included_at_the_lowest_urgency():
    tasks = [_task(id=1, due_at=None)]

    plan = build_recovery_plan(tasks, current_time=NOW)

    assert len(plan) == 1
    assert plan[0].urgency_label == "later"
    assert plan[0].is_overdue is False


def test_clustering_increases_score_but_never_beats_a_more_urgent_task():
    tasks = [
        # Two tasks clustered together, both due later than the single
        # overdue task below.
        _task(id=1, due_at=NOW + timedelta(days=5)),
        _task(id=2, due_at=NOW + timedelta(days=5, hours=2)),
        # A lone overdue task, not clustered with anything.
        _task(id=3, due_at=NOW - timedelta(hours=1)),
    ]

    plan = build_recovery_plan(tasks, current_time=NOW)

    clustered = {p.task.id: p for p in plan if p.task.id in (1, 2)}
    assert clustered[1].cluster_size == 1
    assert clustered[2].cluster_size == 1
    # Clustering bonus is real...
    lone_far_future = build_recovery_plan(
        [_task(id=1, due_at=NOW + timedelta(days=5))], current_time=NOW
    )[0]
    assert clustered[1].score > lone_far_future.score
    # ...but the overdue task still ranks first regardless.
    assert plan[0].task.id == 3


def test_estimated_minutes_overrides_the_task_type_default():
    tasks = [_task(id=1, task_type=TaskType.READING, estimated_minutes=500, due_at=NOW + timedelta(days=1))]

    plan = build_recovery_plan(tasks, current_time=NOW)

    assert plan[0].estimated_effort_minutes == 500


def test_priority_label_thresholds_match_the_score():
    tasks = [
        _task(id=1, title="overdue", due_at=NOW - timedelta(hours=1)),
        _task(id=2, title="due this week", due_at=NOW + timedelta(days=5)),
        _task(id=3, title="later", due_at=NOW + timedelta(days=30)),
    ]

    plan = {p.task.id: p for p in build_recovery_plan(tasks, current_time=NOW)}

    assert plan[1].priority == TaskPriority.URGENT
    assert plan[2].priority == TaskPriority.MEDIUM
    assert plan[3].priority == TaskPriority.LOW


def test_ties_are_broken_by_due_date_then_task_id_for_a_stable_order():
    same_due = NOW + timedelta(days=5)
    tasks = [
        _task(id=2, due_at=same_due),
        _task(id=1, due_at=same_due),
    ]

    plan = build_recovery_plan(tasks, current_time=NOW)

    # Same urgency tier and same cluster size (each other) -> identical
    # score -> id ascending breaks the tie deterministically.
    assert [p.task.id for p in plan] == [1, 2]
