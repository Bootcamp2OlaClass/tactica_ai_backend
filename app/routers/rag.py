from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.exceptions.document import DocumentNotFoundError
from app.exceptions.rag import (
    ChunkEmbeddingAlreadyInProgressError,
    DocumentNotReadyForEmbeddingError,
    EmbeddingNotAvailableError,
    RagError,
)
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.document import DocumentResponse
from app.services.document_embedding_trigger import DocumentEmbeddingTriggerService

router = APIRouter(
    prefix="/api/v1",
    tags=["RAG"],
)

RAG_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Authentication required or invalid",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Document not found",
    },
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "Document not ready, or embedding already in progress",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "AI embedding could not be queued or is not configured",
    },
}


def get_document_embedding_trigger_service(
    db: Session = Depends(get_db),
) -> DocumentEmbeddingTriggerService:
    return DocumentEmbeddingTriggerService(db)


def raise_rag_http_exception(error: Exception) -> NoReturn:
    if isinstance(error, DocumentNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND

    elif isinstance(
        error,
        (DocumentNotReadyForEmbeddingError, ChunkEmbeddingAlreadyInProgressError),
    ):
        status_code = status.HTTP_409_CONFLICT

    elif isinstance(error, EmbeddingNotAvailableError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.post(
    "/documents/{document_id}/embed",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=RAG_ERROR_RESPONSES,
)
def trigger_document_embedding(
    document_id: int = Path(ge=1, description="ID of the document to chunk+embed"),
    current_user: User = Depends(get_current_user),
    service: DocumentEmbeddingTriggerService = Depends(
        get_document_embedding_trigger_service
    ),
) -> DocumentResponse:
    try:
        document = service.trigger_embedding(
            document_id=document_id, user_id=current_user.id
        )
        return DocumentResponse.model_validate(document)
    except (RagError, DocumentNotFoundError) as error:
        raise_rag_http_exception(error)
