"""Pure unit tests for the deterministic week/item computation -- see
PHASE_09_SEMESTER_ROADMAP.md, "Deterministic First, LLM Second." No
database, no LLM: this is calendar/status math and must be exactly right
independent of anything else in the pipeline.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.models.roadmap import RoadmapItemType
from app.models.task import TaskStatus, TaskType
from app.services.roadmap_scheduling import compute_deterministic_items, compute_weeks


def _task(**overrides):
    defaults = dict(
        id=1,
        course_id=10,
        title="Untitled",
        task_type=TaskType.ASSIGNMENT,
        status=TaskStatus.TODO,
        due_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_compute_weeks_produces_fixed_seven_day_buckets():
    weeks = compute_weeks(semester_start=date(2026, 8, 24), semester_end=date(2026, 9, 6))

    assert [w.week_number for w in weeks] == [1, 2]
    assert weeks[0].start_date == date(2026, 8, 24)
    assert weeks[0].end_date == date(2026, 8, 30)
    assert weeks[1].start_date == date(2026, 8, 31)
    assert weeks[1].end_date == date(2026, 9, 6)


def test_compute_weeks_truncates_the_final_week_at_semester_end():
    # 10-day semester -> week 1 full (7 days), week 2 truncated to 3 days,
    # never overrunning semester_end.
    weeks = compute_weeks(semester_start=date(2026, 8, 24), semester_end=date(2026, 9, 2))

    assert len(weeks) == 2
    assert weeks[1].start_date == date(2026, 8, 31)
    assert weeks[1].end_date == date(2026, 9, 2)


def test_compute_weeks_returns_empty_for_an_invalid_range():
    assert compute_weeks(semester_start=date(2026, 9, 1), semester_end=date(2026, 8, 1)) == []


def test_compute_deterministic_items_maps_task_type_to_item_type():
    weeks = compute_weeks(semester_start=date(2026, 8, 24), semester_end=date(2026, 9, 6))
    due = datetime(2026, 8, 25, tzinfo=timezone.utc)

    tasks = [
        _task(id=1, task_type=TaskType.EXAM, title="Midterm", due_at=due),
        _task(id=2, task_type=TaskType.QUIZ, title="Quiz 1", due_at=due),
        _task(id=3, task_type=TaskType.ASSIGNMENT, title="Essay 1", due_at=due),
        _task(id=4, task_type=TaskType.PROJECT, title="Group Project", due_at=due),
        _task(id=5, task_type=TaskType.READING, title="Chapter 3", due_at=due),
        _task(id=6, task_type=TaskType.OTHER, title="Misc", due_at=due),
    ]

    items = compute_deterministic_items(weeks=weeks, tasks=tasks)
    item_types_by_task_id = {item.task_id: item.item_type for item in items}

    assert item_types_by_task_id[1] == RoadmapItemType.EXAM_PREPARATION
    assert item_types_by_task_id[2] == RoadmapItemType.EXAM_PREPARATION
    assert item_types_by_task_id[3] == RoadmapItemType.ASSIGNMENT_PREPARATION
    assert item_types_by_task_id[4] == RoadmapItemType.ASSIGNMENT_PREPARATION
    assert item_types_by_task_id[5] == RoadmapItemType.MILESTONE
    assert item_types_by_task_id[6] == RoadmapItemType.MILESTONE


def test_compute_deterministic_items_excludes_completed_and_cancelled_tasks():
    weeks = compute_weeks(semester_start=date(2026, 8, 24), semester_end=date(2026, 9, 6))
    due = datetime(2026, 8, 25, tzinfo=timezone.utc)

    tasks = [
        _task(id=1, status=TaskStatus.TODO, due_at=due),
        _task(id=2, status=TaskStatus.IN_PROGRESS, due_at=due),
        _task(id=3, status=TaskStatus.COMPLETED, due_at=due),
        _task(id=4, status=TaskStatus.CANCELLED, due_at=due),
    ]

    items = compute_deterministic_items(weeks=weeks, tasks=tasks)

    assert {item.task_id for item in items} == {1, 2}


def test_compute_deterministic_items_excludes_tasks_with_no_due_date():
    weeks = compute_weeks(semester_start=date(2026, 8, 24), semester_end=date(2026, 9, 6))

    tasks = [_task(id=1, due_at=None)]

    assert compute_deterministic_items(weeks=weeks, tasks=tasks) == []


def test_compute_deterministic_items_excludes_out_of_range_deadlines():
    weeks = compute_weeks(semester_start=date(2026, 8, 24), semester_end=date(2026, 9, 6))

    tasks = [
        _task(id=1, due_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),  # before semester
        _task(id=2, due_at=datetime(2027, 1, 1, tzinfo=timezone.utc)),  # after semester
    ]

    assert compute_deterministic_items(weeks=weeks, tasks=tasks) == []


def test_compute_deterministic_items_handles_multiple_deadlines_in_the_same_week():
    # The "conflicting deadlines" case -- multiple real deadlines land in
    # the same week; each becomes its own item, none merged or dropped.
    weeks = compute_weeks(semester_start=date(2026, 8, 24), semester_end=date(2026, 8, 30))
    due = datetime(2026, 8, 26, tzinfo=timezone.utc)

    tasks = [
        _task(id=1, title="Essay", task_type=TaskType.ASSIGNMENT, due_at=due),
        _task(id=2, title="Midterm", task_type=TaskType.EXAM, due_at=due),
    ]

    items = compute_deterministic_items(weeks=weeks, tasks=tasks)

    assert len(items) == 2
    assert all(item.week_number == 1 for item in items)
    assert {item.task_id for item in items} == {1, 2}


def test_compute_deterministic_items_titles_are_task_type_specific():
    weeks = compute_weeks(semester_start=date(2026, 8, 24), semester_end=date(2026, 8, 30))
    due = datetime(2026, 8, 25, tzinfo=timezone.utc)

    tasks = [
        _task(id=1, title="Midterm", task_type=TaskType.EXAM, due_at=due),
        _task(id=2, title="Essay 1", task_type=TaskType.ASSIGNMENT, due_at=due),
        _task(id=3, title="Chapter 3", task_type=TaskType.READING, due_at=due),
    ]

    items = {item.task_id: item.title for item in compute_deterministic_items(weeks=weeks, tasks=tasks)}

    assert items[1] == "Prepare for Midterm"
    assert items[2] == "Work on Essay 1"
    assert items[3] == "Chapter 3"  # MILESTONE keeps the task's own title verbatim
