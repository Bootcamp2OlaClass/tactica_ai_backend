class ChatError(Exception):
    """Base exception for chat/conversation operations."""


class ConversationNotFoundError(ChatError):
    """Raised when a conversation doesn't exist or isn't owned by the
    requesting user."""


class ChatNotAvailableError(ChatError):
    """Raised when no LLM provider is configured, or the provider is
    temporarily unreachable at request time."""
