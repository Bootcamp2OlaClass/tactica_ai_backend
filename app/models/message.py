from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class MessageRole(str, Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class Message(Base):
    """One turn in a Conversation — see PHASE_08_AI_STUDY_COACH.md.

    `citations`/`grounded` are only ever populated on ASSISTANT messages
    (the Return step of the Retrieve->Generate->Validate->Ground-truth-
    filter->Return pipeline persists them there); a USER message is the
    student's own question, verbatim, with no such fields.
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[MessageRole] = mapped_column(
        SQLEnum(MessageRole, name="messagerole"),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    grounded: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        default=None,
    )

    citations: Mapped[list[dict] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
