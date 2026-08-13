"""Deterministic week/item computation for the semester roadmap — see
PHASE_09_SEMESTER_ROADMAP.md, "Deterministic First, LLM Second."

Pure functions of the semester's own dates and the student's real Task
rows -- no LLM call anywhere in this module. Week boundaries, which week a
deadline falls in, and whether something counts as "still needs prep" are
all calendar/status math, not judgment calls a model should be making.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.models.roadmap import RoadmapItemType
from app.models.task import Task, TaskStatus, TaskType

DAYS_PER_WEEK = 7

# Tasks in these statuses represent completed/abandoned work -- nothing
# left to prepare for, so they're excluded from a forward-looking roadmap
# (the roadmap answers "what do I still need to do," not "what happened").
_SCHEDULABLE_STATUSES = (TaskStatus.TODO, TaskStatus.IN_PROGRESS)

_EXAM_LIKE_TYPES = {TaskType.EXAM, TaskType.QUIZ}
_ASSIGNMENT_LIKE_TYPES = {TaskType.ASSIGNMENT, TaskType.PROJECT, TaskType.PRESENTATION}


def _item_type_for(task_type: TaskType) -> RoadmapItemType:
    if task_type in _EXAM_LIKE_TYPES:
        return RoadmapItemType.EXAM_PREPARATION
    if task_type in _ASSIGNMENT_LIKE_TYPES:
        return RoadmapItemType.ASSIGNMENT_PREPARATION
    return RoadmapItemType.MILESTONE


def _title_for(task: Task, item_type: RoadmapItemType) -> str:
    if item_type == RoadmapItemType.EXAM_PREPARATION:
        return f"Prepare for {task.title}"
    if item_type == RoadmapItemType.ASSIGNMENT_PREPARATION:
        return f"Work on {task.title}"
    return task.title


@dataclass(frozen=True)
class WeekDraft:
    week_number: int
    start_date: date
    end_date: date


@dataclass(frozen=True)
class ItemDraft:
    week_number: int
    item_type: RoadmapItemType
    title: str
    task_id: int
    course_id: int
    due_date: date


def compute_weeks(*, semester_start: date, semester_end: date) -> list[WeekDraft]:
    """Fixed 7-day buckets starting at the semester's own start date. The
    final week is truncated to semester_end rather than overrunning it --
    a roadmap week never extends past the semester itself."""

    if semester_end < semester_start:
        return []

    weeks: list[WeekDraft] = []
    week_number = 1
    cursor = semester_start

    while cursor <= semester_end:
        week_end = min(cursor + timedelta(days=DAYS_PER_WEEK - 1), semester_end)
        weeks.append(WeekDraft(week_number=week_number, start_date=cursor, end_date=week_end))
        cursor = week_end + timedelta(days=1)
        week_number += 1

    return weeks


def _week_number_for_date(weeks: list[WeekDraft], target: date) -> int | None:
    for week in weeks:
        if week.start_date <= target <= week.end_date:
            return week.week_number
    return None


def compute_deterministic_items(
    *, weeks: list[WeekDraft], tasks: list[Task]
) -> list[ItemDraft]:
    """One item per still-open, in-range task with a real due date. Tasks
    with no due_at, tasks already completed/cancelled, and tasks whose due
    date falls outside every computed week (before the semester starts or
    after it ends) are all deliberately excluded -- not guessed at."""

    drafts: list[ItemDraft] = []

    for task in tasks:
        if task.status not in _SCHEDULABLE_STATUSES:
            continue
        if task.due_at is None:
            continue

        due_date = task.due_at.date()
        week_number = _week_number_for_date(weeks, due_date)
        if week_number is None:
            continue

        item_type = _item_type_for(task.task_type)
        drafts.append(
            ItemDraft(
                week_number=week_number,
                item_type=item_type,
                title=_title_for(task, item_type),
                task_id=task.id,
                course_id=task.course_id,
                due_date=due_date,
            )
        )

    return drafts
