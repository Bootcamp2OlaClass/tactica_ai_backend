from sqlalchemy.orm import Session

from app.exceptions.chat import ConversationNotFoundError
from app.models.conversation import Conversation
from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository


class ChatQueryService:
    """Read-only, ownership-checked conversation listing/detail -- mirrors
    ExtractionQueryService's shape."""

    def __init__(
        self,
        db: Session,
        conversation_repository: ConversationRepository | None = None,
    ) -> None:
        self.db = db
        self.conversation_repository = (
            conversation_repository or ConversationRepository(db)
        )

    def list_conversations(self, *, user_id: int) -> list[Conversation]:
        return self.conversation_repository.list_by_user(user_id=user_id)

    def get_conversation(
        self, *, conversation_id: int, user_id: int
    ) -> tuple[Conversation, list[Message]]:
        conversation = self.conversation_repository.get_owned_by_id(
            conversation_id=conversation_id, user_id=user_id
        )
        if conversation is None:
            raise ConversationNotFoundError("Conversation not found.")

        messages = self.conversation_repository.list_messages(
            conversation_id=conversation.id
        )
        return conversation, messages
