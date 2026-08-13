"""Google Calendar sync models — see PHASE_12_CALENDAR.md.

`CalendarConnection` holds the student's OAuth tokens (Calendar scope
only, independent of ADR-001's identity/login decision). Tokens are
encrypted at rest (Phase 14, see app/core/token_encryption.py) —
transparent to every read/write call site, since EncryptedText decrypts
on load and encrypts on save.

`CalendarSync` is the idempotency anchor: one row per synced `Task`,
keyed by the provider's own event id. `CalendarSyncService` (see
app/services/calendar_sync.py) is the only writer -- its logic, not a DB
constraint, is what prevents duplicate events (update when a row with a
provider_event_id already exists, create only when it doesn't).
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.token_encryption import EncryptedText
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.user import User


class CalendarSyncStatus(str, Enum):
    SYNCED = "SYNCED"
    FAILED = "FAILED"


class CalendarConnection(Base):
    __tablename__ = "calendar_connections"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_calendar_connection_one_per_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    access_token: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    refresh_token: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship()


class CalendarSync(Base):
    __tablename__ = "calendar_syncs"

    __table_args__ = (
        UniqueConstraint("task_id", name="uq_calendar_sync_one_per_task"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    sync_status: Mapped[CalendarSyncStatus] = mapped_column(
        SQLEnum(CalendarSyncStatus, name="calendarsyncstatus"), nullable=False
    )
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    task: Mapped["Task"] = relationship()
