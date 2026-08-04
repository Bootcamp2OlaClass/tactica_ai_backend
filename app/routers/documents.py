from datetime import datetime
from typing import NoReturn

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.exceptions.course import CourseNotFoundError
from app.exceptions.document import (
    DocumentError,
    DocumentFileMissingError,
    DocumentNotFoundError,
    DuplicateDocumentError,
    FileStorageError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.models.document import (
    DocumentType,
    ProcessingStatus,
)
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
)
from app.services.document_query import DocumentQueryService
from app.services.document_upload import DocumentUploadService


router = APIRouter(
    prefix="/api/v1",
    tags=["Documents"],
)


DOCUMENT_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {
        "model": ErrorResponse,
        "description": "Invalid document file, filter, or request",
    },
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Authentication required or invalid",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Document or course not found",
    },
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "Duplicate document",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "Document storage or download failure",
    },
}


def get_document_query_service(
    db: Session = Depends(get_db),
) -> DocumentQueryService:
    return DocumentQueryService(db)


def get_document_upload_service(
    db: Session = Depends(get_db),
) -> DocumentUploadService:
    return DocumentUploadService(db)


def raise_document_http_exception(
    error: Exception,
) -> NoReturn:
    if isinstance(
        error,
        (
            CourseNotFoundError,
            DocumentNotFoundError,
            DocumentFileMissingError,
        ),
    ):
        status_code = status.HTTP_404_NOT_FOUND

    elif isinstance(error, DuplicateDocumentError):
        status_code = status.HTTP_409_CONFLICT

    elif isinstance(
        error,
        (
            UnsupportedFileTypeError,
            FileTooLargeError,
        ),
    ):
        status_code = status.HTTP_400_BAD_REQUEST

    elif isinstance(error, FileStorageError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    raise HTTPException(
        status_code=status_code,
        detail=str(error),
    ) from error


@router.post(
    "/courses/{course_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses=DOCUMENT_ERROR_RESPONSES,
)
async def upload_course_document(
    course_id: int = Path(
        ge=1,
        description="ID of the course receiving the document",
    ),
    uploaded_file: UploadFile = File(
        ...,
        alias="file",
        description="Academic document file",
    ),
    document_type: DocumentType = Form(
        default=DocumentType.OTHER,
        description="Academic document type",
    ),
    current_user: User = Depends(get_current_user),
    service: DocumentUploadService = Depends(
        get_document_upload_service
    ),
) -> DocumentResponse:
    try:
        document = await service.upload_document(
            course_id=course_id,
            user_id=current_user.id,
            uploaded_file=uploaded_file,
            document_type=document_type,
        )

        return DocumentResponse.model_validate(document)

    except (
        CourseNotFoundError,
        DocumentError,
    ) as error:
        raise_document_http_exception(error)


@router.get(
    "/courses/{course_id}/documents",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    responses=DOCUMENT_ERROR_RESPONSES,
)
def list_course_documents(
    course_id: int = Path(
        ge=1,
        description="ID of the course whose documents are requested",
    ),
    document_type: DocumentType | None = Query(
        default=None,
        description="Filter documents by document type",
    ),
    processing_status: ProcessingStatus | None = Query(
        default=None,
        description="Filter documents by processing status",
    ),
    search: str | None = Query(
        default=None,
        max_length=255,
        description="Search by original file name",
    ),
    uploaded_from: datetime | None = Query(
        default=None,
        description="Return documents uploaded on or after this timestamp",
    ),
    uploaded_to: datetime | None = Query(
        default=None,
        description="Return documents uploaded on or before this timestamp",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number starting from 1",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of documents returned per page",
    ),
    current_user: User = Depends(get_current_user),
    service: DocumentQueryService = Depends(
        get_document_query_service
    ),
) -> DocumentListResponse:
    if (
        uploaded_from is not None
        and uploaded_to is not None
        and uploaded_from > uploaded_to
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "uploaded_from must be earlier than or equal to "
                "uploaded_to."
            ),
        )

    try:
        return service.list_course_documents(
            course_id=course_id,
            user_id=current_user.id,
            document_type=document_type,
            processing_status=processing_status,
            file_name_search=search,
            uploaded_from=uploaded_from,
            uploaded_to=uploaded_to,
            page=page,
            page_size=page_size,
        )

    except (
        CourseNotFoundError,
        DocumentError,
    ) as error:
        raise_document_http_exception(error)


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    responses=DOCUMENT_ERROR_RESPONSES,
)
def get_document(
    document_id: int = Path(
        ge=1,
        description="ID of the requested document",
    ),
    current_user: User = Depends(get_current_user),
    service: DocumentQueryService = Depends(
        get_document_query_service
    ),
) -> DocumentResponse:
    try:
        document = service.get_document(
            document_id=document_id,
            user_id=current_user.id,
        )

        return DocumentResponse.model_validate(document)

    except DocumentError as error:
        raise_document_http_exception(error)


@router.get(
    "/documents/{document_id}/download",
    response_class=FileResponse,
    status_code=status.HTTP_200_OK,
    responses=DOCUMENT_ERROR_RESPONSES,
)
def download_document(
    document_id: int = Path(
        ge=1,
        description="ID of the document to download",
    ),
    current_user: User = Depends(get_current_user),
    service: DocumentQueryService = Depends(
        get_document_query_service
    ),
) -> FileResponse:
    try:
        file_path, document = service.get_document_download(
            document_id=document_id,
            user_id=current_user.id,
        )

        return FileResponse(
            path=file_path,
            media_type=document.mime_type,
            filename=document.original_file_name,
        )

    except DocumentError as error:
        raise_document_http_exception(error)