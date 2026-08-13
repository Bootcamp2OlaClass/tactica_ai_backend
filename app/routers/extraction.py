from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.exceptions.document import DocumentNotFoundError
from app.exceptions.extraction import (
    DocumentNotReadyForExtractionError,
    ExtractionAlreadyInProgressError,
    ExtractionCandidateAlreadyReviewedError,
    ExtractionCandidateNotFoundError,
    ExtractionError,
    ExtractionNotAvailableError,
)
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.document import DocumentResponse
from app.schemas.extraction_candidate import (
    ExtractionCandidateListResponse,
    ExtractionCandidateResponse,
)
from app.services.document_extraction_trigger import DocumentExtractionTriggerService
from app.services.extraction_query import ExtractionQueryService
from app.services.extraction_review import ExtractionReviewService

router = APIRouter(
    prefix="/api/v1",
    tags=["Extraction"],
)

EXTRACTION_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Authentication required or invalid",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Document or candidate not found",
    },
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "Document not ready, extraction already in progress, "
        "or candidate already reviewed",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "AI extraction could not be queued or is not configured",
    },
}


def get_document_extraction_trigger_service(
    db: Session = Depends(get_db),
) -> DocumentExtractionTriggerService:
    return DocumentExtractionTriggerService(db)


def get_extraction_query_service(
    db: Session = Depends(get_db),
) -> ExtractionQueryService:
    return ExtractionQueryService(db)


def get_extraction_review_service(
    db: Session = Depends(get_db),
) -> ExtractionReviewService:
    return ExtractionReviewService(db)


def raise_extraction_http_exception(error: Exception) -> NoReturn:
    if isinstance(
        error,
        (DocumentNotFoundError, ExtractionCandidateNotFoundError),
    ):
        status_code = status.HTTP_404_NOT_FOUND

    elif isinstance(
        error,
        (
            DocumentNotReadyForExtractionError,
            ExtractionAlreadyInProgressError,
            ExtractionCandidateAlreadyReviewedError,
        ),
    ):
        status_code = status.HTTP_409_CONFLICT

    elif isinstance(error, ExtractionNotAvailableError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.post(
    "/documents/{document_id}/extract",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=EXTRACTION_ERROR_RESPONSES,
)
def trigger_document_extraction(
    document_id: int = Path(ge=1, description="ID of the document to extract"),
    current_user: User = Depends(get_current_user),
    service: DocumentExtractionTriggerService = Depends(
        get_document_extraction_trigger_service
    ),
) -> DocumentResponse:
    try:
        document = service.trigger_extraction(
            document_id=document_id, user_id=current_user.id
        )
        return DocumentResponse.model_validate(document)
    except (ExtractionError, DocumentNotFoundError) as error:
        raise_extraction_http_exception(error)


@router.get(
    "/documents/{document_id}/extraction-candidates",
    response_model=ExtractionCandidateListResponse,
    status_code=status.HTTP_200_OK,
    responses=EXTRACTION_ERROR_RESPONSES,
)
def list_document_extraction_candidates(
    document_id: int = Path(ge=1, description="ID of the document"),
    current_user: User = Depends(get_current_user),
    service: ExtractionQueryService = Depends(get_extraction_query_service),
) -> ExtractionCandidateListResponse:
    try:
        candidates = service.list_candidates(
            document_id=document_id, user_id=current_user.id
        )
        return ExtractionCandidateListResponse(
            items=[
                ExtractionCandidateResponse.model_validate(candidate)
                for candidate in candidates
            ]
        )
    except DocumentNotFoundError as error:
        raise_extraction_http_exception(error)


@router.post(
    "/extraction-candidates/{candidate_id}/accept",
    response_model=ExtractionCandidateResponse,
    status_code=status.HTTP_200_OK,
    responses=EXTRACTION_ERROR_RESPONSES,
)
def accept_extraction_candidate(
    candidate_id: int = Path(ge=1, description="ID of the candidate to accept"),
    current_user: User = Depends(get_current_user),
    service: ExtractionReviewService = Depends(get_extraction_review_service),
) -> ExtractionCandidateResponse:
    try:
        candidate = service.accept(candidate_id=candidate_id, user_id=current_user.id)
        return ExtractionCandidateResponse.model_validate(candidate)
    except ExtractionError as error:
        raise_extraction_http_exception(error)


@router.post(
    "/extraction-candidates/{candidate_id}/reject",
    response_model=ExtractionCandidateResponse,
    status_code=status.HTTP_200_OK,
    responses=EXTRACTION_ERROR_RESPONSES,
)
def reject_extraction_candidate(
    candidate_id: int = Path(ge=1, description="ID of the candidate to reject"),
    current_user: User = Depends(get_current_user),
    service: ExtractionReviewService = Depends(get_extraction_review_service),
) -> ExtractionCandidateResponse:
    try:
        candidate = service.reject(candidate_id=candidate_id, user_id=current_user.id)
        return ExtractionCandidateResponse.model_validate(candidate)
    except ExtractionError as error:
        raise_extraction_http_exception(error)
