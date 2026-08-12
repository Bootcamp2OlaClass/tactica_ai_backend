import logging
from datetime import datetime
from math import ceil

from sqlalchemy.orm import Session

from app.core.config import settings
from app.exceptions.course import CourseNotFoundError
from app.exceptions.document import (
    DocumentFileMissingError,
    DocumentNotFoundError,
)
from app.models.document import (
    Document,
    DocumentType,
    ProcessingStatus,
)
from app.repositories import course_repository
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
)
from app.services.storage import StorageProvider, get_storage_provider


logger = logging.getLogger(__name__)


class DocumentQueryService:
    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository | None = None,
        storage_service: StorageProvider | None = None,
    ) -> None:
        self.db = db

        self.document_repository = (
            document_repository
            if document_repository is not None
            else DocumentRepository(db)
        )

        self.storage_service = (
            storage_service
            if storage_service is not None
            else get_storage_provider(settings)
        )

    def _get_owned_course(
        self,
        course_id: int,
        user_id: int,
    ) -> None:
        course = course_repository.get_course_by_id(
            db=self.db,
            course_id=course_id,
            user_id=user_id,
        )

        if course is None:
            raise CourseNotFoundError("Course not found.")

    def list_course_documents(
        self,
        *,
        course_id: int,
        user_id: int,
        document_type: DocumentType | None = None,
        processing_status: ProcessingStatus | None = None,
        file_name_search: str | None = None,
        uploaded_from: datetime | None = None,
        uploaded_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> DocumentListResponse:
        self._get_owned_course(
            course_id=course_id,
            user_id=user_id,
        )

        offset = (page - 1) * page_size

        documents = self.document_repository.list_by_course(
            course_id=course_id,
            document_type=document_type,
            processing_status=processing_status,
            file_name_search=file_name_search,
            uploaded_from=uploaded_from,
            uploaded_to=uploaded_to,
            offset=offset,
            limit=page_size,
        )

        total = self.document_repository.count_by_course(
            course_id=course_id,
            document_type=document_type,
            processing_status=processing_status,
            file_name_search=file_name_search,
            uploaded_from=uploaded_from,
            uploaded_to=uploaded_to,
        )

        total_pages = ceil(total / page_size) if total > 0 else 0

        return DocumentListResponse(
            items=[
                DocumentResponse.model_validate(document)
                for document in documents
            ],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )

    def get_document(
        self,
        *,
        document_id: int,
        user_id: int,
    ) -> Document:
        document = self.document_repository.get_active_by_id(
            document_id=document_id,
        )

        if document is None:
            raise DocumentNotFoundError("Document not found.")

        course = course_repository.get_course_by_id(
            db=self.db,
            course_id=document.course_id,
            user_id=user_id,
        )

        if course is None:
            raise DocumentNotFoundError("Document not found.")

        return document

    def get_document_download(
        self,
        *,
        document_id: int,
        user_id: int,
    ) -> tuple[bytes, Document]:
        document = self.get_document(
            document_id=document_id,
            user_id=user_id,
        )

        try:
            file_content = self.storage_service.load(
                document.storage_path,
            )

        except FileNotFoundError as error:
            logger.error(
                "Document download failed: physical file missing",
                extra={
                    "document_id": document.id,
                    "course_id": document.course_id,
                    "user_id": user_id,
                },
            )

            raise DocumentFileMissingError(
                "The document file is unavailable."
            ) from error

        except ValueError as error:
            logger.error(
                "Document download failed: invalid storage path",
                extra={
                    "document_id": document.id,
                    "course_id": document.course_id,
                    "user_id": user_id,
                },
            )

            raise DocumentFileMissingError(
                "The document file is unavailable."
            ) from error

        logger.info(
            "Document downloaded",
            extra={
                "document_id": document.id,
                "course_id": document.course_id,
                "user_id": user_id,
                "original_file_name": document.original_file_name,
                "mime_type": document.mime_type,
            },
        )

        return file_content, document