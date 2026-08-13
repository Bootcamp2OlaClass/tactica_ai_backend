"""Pure deterministic recovery-plan detection/prioritization — see
PHASE_10_SMART_PLANNING.md.

No DB, no LLM: overdue detection, deadline-clustering, and priority
scoring are all calendar/status math over the student's own Task rows --
reproducible without any LLM call, this phase's explicit acceptance
criterion. The LLM layer (app/services/recovery_plan_generation.py) only
ever adds explanatory text on top of the order this module computes; it
never re-ranks anything.

Unlike Phase 09's roadmap (which only schedules tasks with a real due
date, since it's placing them into calendar weeks), a recovery plan's job
is comprehensive triage of all incomplete work -- a task with no due date
still needs to be surfaced, just at the lowest urgency tier, not silently
dropped.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models.task import Task, TaskPriority, TaskStatus, TaskType

_SCHEDULABLE_STATUSES = (TaskStatus.TODO, TaskStatus.IN_PROGRESS)

CLUSTER_WINDOW_DAYS = 3

DEFAULT_EFFORT_MINUTES_BY_TYPE: dict[TaskType, int] = {
    TaskType.EXAM: 240,
    TaskType.PROJECT: 300,
    TaskType.PRESENTATION: 120,
    TaskType.ASSIGNMENT: 120,
    TaskType.QUIZ: 60,
    TaskType.READING: 45,
    TaskType.OTHER: 60,
}

# Urgency tiers -- the dominant term in the score, so the plan is always
# overdue-first regardless of clustering/effort.
URGENCY_OVERDUE = 100.0
URGENCY_WITHIN_1_DAY = 80.0
URGENCY_WITHIN_3_DAYS = 60.0
URGENCY_WITHIN_7_DAYS = 40.0
URGENCY_LATER = 10.0

# Workload-clustering bonus: each other incomplete task due within
# CLUSTER_WINDOW_DAYS adds weight, capped so clustering alone can never
# outrank a more urgent, unclustered deadline.
CLUSTER_BONUS_PER_TASK = 15.0
CLUSTER_BONUS_MAX = 45.0

# Effort/time-remaining ("cram intensity") tiebreaker -- capped low on
# purpose so it only ever breaks ties within an urgency tier, never
# overrides urgency or clustering.
EFFORT_URGENCY_CAP = 20.0


@dataclass(frozen=True)
class PrioritizedTask:
    task: Task
    score: float
    urgency_label: str  # "overdue" | "due_soon" | "due_this_week" | "later"
    is_overdue: bool
    cluster_size: int
    estimated_effort_minutes: int
    priority: TaskPriority


def _urgency(task: Task, now: datetime) -> tuple[float, str]:
    if task.due_at is None:
        return URGENCY_LATER, "later"

    delta = task.due_at - now
    if delta.total_seconds() < 0:
        return URGENCY_OVERDUE, "overdue"
    if delta <= timedelta(days=1):
        return URGENCY_WITHIN_1_DAY, "due_soon"
    if delta <= timedelta(days=3):
        return URGENCY_WITHIN_3_DAYS, "due_soon"
    if delta <= timedelta(days=7):
        return URGENCY_WITHIN_7_DAYS, "due_this_week"
    return URGENCY_LATER, "later"


def _cluster_size(task: Task, all_tasks: list[Task]) -> int:
    if task.due_at is None:
        return 0

    window = timedelta(days=CLUSTER_WINDOW_DAYS)
    return sum(
        1
        for other in all_tasks
        if other.id != task.id
        and other.due_at is not None
        and abs(other.due_at - task.due_at) <= window
    )


def _effort_minutes(task: Task) -> int:
    if task.estimated_minutes is not None:
        return task.estimated_minutes
    return DEFAULT_EFFORT_MINUTES_BY_TYPE.get(task.task_type, 60)


def _priority_label(score: float) -> TaskPriority:
    if score >= 100:
        return TaskPriority.URGENT
    if score >= 60:
        return TaskPriority.HIGH
    if score >= 40:
        return TaskPriority.MEDIUM
    return TaskPriority.LOW


def build_recovery_plan(
    tasks: list[Task], *, current_time: datetime
) -> list[PrioritizedTask]:
    """workload (clustering) -> deadline urgency -> estimated effort ->
    priority, per the phase brief's own pipeline naming. ("Available
    study time" is deliberately not a term in this formula -- no calendar/
    availability data exists anywhere in this codebase yet, see
    PHASE_10_SMART_PLANNING.md's Remaining Limitations; introducing a
    fabricated "hours free today" number would be worse than omitting the
    signal honestly.)

    Sorted by score descending; ties broken by due_at ascending (earlier
    deadlines first) then task id ascending, for a fully stable,
    reproducible order -- no LLM call anywhere in this function.
    """

    schedulable = [task for task in tasks if task.status in _SCHEDULABLE_STATUSES]

    prioritized: list[PrioritizedTask] = []
    for task in schedulable:
        urgency_score, urgency_label = _urgency(task, current_time)
        cluster_size = _cluster_size(task, schedulable)
        cluster_bonus = min(cluster_size * CLUSTER_BONUS_PER_TASK, CLUSTER_BONUS_MAX)
        effort_minutes = _effort_minutes(task)

        if task.due_at is not None:
            days_remaining = max((task.due_at - current_time).total_seconds() / 86400, 0.1)
        else:
            days_remaining = 999.0
        effort_score = min(effort_minutes / days_remaining / 10, EFFORT_URGENCY_CAP)

        score = urgency_score + cluster_bonus + effort_score

        prioritized.append(
            PrioritizedTask(
                task=task,
                score=score,
                urgency_label=urgency_label,
                is_overdue=urgency_label == "overdue",
                cluster_size=cluster_size,
                estimated_effort_minutes=effort_minutes,
                priority=_priority_label(score),
            )
        )

    far_future = datetime.max.replace(tzinfo=current_time.tzinfo)
    prioritized.sort(key=lambda p: (-p.score, p.task.due_at or far_future, p.task.id))
    return prioritized
