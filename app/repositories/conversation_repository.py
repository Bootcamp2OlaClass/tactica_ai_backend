from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole


class ConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, *, user_id: int, title: str | None = None) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        self.db.add(conversation)
        self.db.flush()
        return conversation

    def get_owned_by_id(
        self, *, conversation_id: int, user_id: int
    ) -> Conversation | None:
        """Ownership-checked lookup -- the only way this repository ever
        hands back a Conversation, mirroring every other owned-entity
        repository in this codebase (course_repository.get_course_by_id,
        Phase 06's `_get_owned_candidate`, etc.)."""
        return (
            self.db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.is_deleted.is_(False),
            )
            .first()
        )

    def list_by_user(self, *, user_id: int, limit: int = 50) -> list[Conversation]:
        return (
            self.db.query(Conversation)
            .filter(
                Conversation.user_id == user_id,
                Conversation.is_deleted.is_(False),
            )
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .all()
        )

    def touch(self, conversation: Conversation) -> None:
        """Bumps `updated_at` so the conversation list can sort by recent
        activity. The model's `onupdate=func.now()` only fires when a
        column on `Conversation` itself is written -- adding rows to the
        separate `messages` table doesn't trigger it, so this is set
        explicitly, once per turn, after both messages are added.

        Uses the database's own clock (`func.now()`, a SQL expression
        evaluated server-side), not `datetime.now()` in Python -- the two
        can disagree by more than a trivial rounding error (observed
        directly: a Docker-container Postgres clock and the test-runner
        host clock drifted by over a second in this environment), which
        would otherwise make `updated_at` an unreliable sort key exactly
        when it matters (ordering conversations by recent activity)."""
        conversation.updated_at = func.now()
        self.db.flush()
        self.db.refresh(conversation)

    def add_message(
        self,
        *,
        conversation_id: int,
        role: MessageRole,
        content: str,
        grounded: bool | None = None,
        citations: list[dict] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            grounded=grounded,
            citations=citations,
        )
        self.db.add(message)
        self.db.flush()
        return message

    def list_messages(self, *, conversation_id: int) -> list[Message]:
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.id.asc())
            .all()
        )
