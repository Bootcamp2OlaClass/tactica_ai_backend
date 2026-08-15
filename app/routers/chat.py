import json
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.rate_limit import user_rate_limiter
from app.core.config import get_settings
from app.db.session import get_db
from app.exceptions.chat import ChatNotAvailableError, ConversationNotFoundError
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    MessageResponse,
)
from app.schemas.common import ErrorResponse
from app.services.chat import ChatService
from app.services.chat_query import ChatQueryService
from app.services.llm import LLMExtractionError, LLMTransientError

router = APIRouter(
    prefix="/api/v1",
    tags=["Chat"],
)

chat_rate_limit = user_rate_limiter(
    key_prefix="chat", max_requests=20, window_seconds=60
)

CHAT_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Authentication required or invalid",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Conversation not found",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "AI chat is not available right now",
    },
}


def get_chat_service(db: Session = Depends(get_db)) -> ChatService:
    return ChatService(db, get_settings())


def get_chat_query_service(db: Session = Depends(get_db)) -> ChatQueryService:
    return ChatQueryService(db)


def raise_chat_http_exception(error: Exception) -> NoReturn:
    if isinstance(error, ConversationNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(
        error, (ChatNotAvailableError, LLMTransientError, LLMExtractionError)
    ):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    responses=CHAT_ERROR_RESPONSES,
)
def send_chat_message(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
    _rate_limit: None = Depends(chat_rate_limit),
) -> ChatResponse:
    try:
        conversation, message = service.send_message(
            user_id=current_user.id,
            message=body.message,
            conversation_id=body.conversation_id,
            course_id=body.course_id,
        )
    except (
        ConversationNotFoundError,
        ChatNotAvailableError,
        LLMTransientError,
        LLMExtractionError,
    ) as error:
        raise_chat_http_exception(error)

    return ChatResponse(
        conversation=ConversationResponse.model_validate(conversation),
        message=MessageResponse.model_validate(message),
    )


@router.post(
    "/chat/stream",
    responses=CHAT_ERROR_RESPONSES,
)
def stream_chat_message(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
    _rate_limit: None = Depends(chat_rate_limit),
) -> StreamingResponse:
    """Same pipeline as POST /chat, streamed as Server-Sent Events.

    The full Retrieve->Generate->Validate->Ground-truth-filter->Return pass
    runs to completion, and the message is persisted, *before* anything is
    streamed -- grounding validation needs the complete answer to check
    citations against, so there is no safe way to stream raw, unvalidated
    model tokens for a feature whose entire acceptance criteria is "never
    fabricate." What streams is the already-validated, already-persisted
    answer text, delivered incrementally for UI responsiveness; a final
    event carries the structured metadata (citations, grounded, ids) the
    client needs once the text is fully rendered.
    """
    try:
        conversation, message = service.send_message(
            user_id=current_user.id,
            message=body.message,
            conversation_id=body.conversation_id,
            course_id=body.course_id,
        )
    except (
        ConversationNotFoundError,
        ChatNotAvailableError,
        LLMTransientError,
        LLMExtractionError,
    ) as error:
        raise_chat_http_exception(error)

    def event_stream():
        words = message.content.split(" ")
        for index, word in enumerate(words):
            delta = word if index == 0 else f" {word}"
            yield f"data: {json.dumps({'delta': delta})}\n\n"

        final_event = {
            "done": True,
            "conversation_id": conversation.id,
            "message_id": message.id,
            "grounded": message.grounded,
            "answer_mode": message.answer_mode.value if message.answer_mode else None,
            "citations": message.citations or [],
        }
        yield f"data: {json.dumps(final_event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get(
    "/chat/conversations",
    response_model=ConversationListResponse,
    status_code=status.HTTP_200_OK,
    responses=CHAT_ERROR_RESPONSES,
)
def list_conversations(
    current_user: User = Depends(get_current_user),
    service: ChatQueryService = Depends(get_chat_query_service),
) -> ConversationListResponse:
    conversations = service.list_conversations(user_id=current_user.id)
    return ConversationListResponse(
        items=[
            ConversationResponse.model_validate(conversation)
            for conversation in conversations
        ]
    )


@router.get(
    "/chat/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_200_OK,
    responses=CHAT_ERROR_RESPONSES,
)
def get_conversation(
    conversation_id: int = Path(ge=1, description="ID of the conversation"),
    current_user: User = Depends(get_current_user),
    service: ChatQueryService = Depends(get_chat_query_service),
) -> ConversationDetailResponse:
    try:
        conversation, messages = service.get_conversation(
            conversation_id=conversation_id, user_id=current_user.id
        )
    except ConversationNotFoundError as error:
        raise_chat_http_exception(error)

    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )
