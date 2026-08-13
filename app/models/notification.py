"""Notification preference/log models — see PHASE_13_NOTIFICATIONS.md.

`NotificationPreference` is opt-out, not opt-in: no row for a given
(user, type) pair means enabled (see NotificationService.is_enabled) --
matches the acceptance criteria's framing ("can opt out per notification
type"), not an opt-in default nobody would see reminders under.

`NotificationLog`'s unique constraint on (user_id, notification_type,
reference_id) is the dedup mechanism's DB-level backstop; the
application-level check in NotificationService.send_reminder is the
primary guard, this is the belt-and-suspenders second layer (matches
CalendarSync's task_id unique constraint's role in Phase 12).
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class NotificationType(str, Enum):
    ASSIGNMENT_DUE = "ASSIGNMENT_DUE"
    EXAM_COUNTDOWN = "EXAM_COUNTDOWN"
    WEEKLY_PLAN = "WEEKLY_PLAN"
    OVERDUE_TASK = "OVERDUE_TASK"
    RECOVERY_PLAN = "RECOVERY_PLAN"


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    __table_args__ = (
        UniqueConstraint(
            "user_id", "notification_type", name="uq_notification_pref_user_type"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType, name="notificationtype"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship()


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    __table_args__ = (
        UniqueConstraint(
            "user_id", "notification_type", "reference_id",
            name="uq_notification_log_dedup",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType, name="notificationtype"), nullable=False
    )
    # The event this send is about (e.g. a task id) -- always a real,
    # stable identifier, never a timestamp, so the same event can never
    # be re-sent even across separate scheduled-job runs.
    reference_id: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship()
