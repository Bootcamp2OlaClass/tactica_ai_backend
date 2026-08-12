import hashlib
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.exceptions.course import CourseNotFoundError
from app.exceptions.document import (
    DuplicateDocumentError,
    FileStorageError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.models.document import (
    Document,
    DocumentType,
    ProcessingStatus,
)
from app.repositories import course_repository
from app.repositories.document_repository import DocumentRepository
from app.services.storage import StorageProvider, get_storage_provider
from app.worker.tasks.documents import process_document


logger = logging.getLogger(__name__)


ALLOWED_MIME_TYPES = {
    "application/pdf",
}

MIME_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
}


class DocumentUploadService:
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

    def _validate_mime_type(
        self,
        mime_type: str,
    ) -> None:
        if mime_type not in ALLOWED_MIME_TYPES:
            raise UnsupportedFileTypeError(
                f"Unsupported file type: {mime_type}"
            )

    def _validate_file_size(
        self,
        file_size: int,
    ) -> None:
        if file_size > settings.max_upload_size:
            raise FileTooLargeError(
                "Uploaded file exceeds the maximum allowed size."
            )

    def _sanitize_original_file_name(
        self,
        original_file_name: str,
    ) -> str:
        normalized_name = original_file_name.replace("\\", "/")
        safe_name = Path(normalized_name).name.strip()

        if not safe_name:
            return "uploaded-file"

        return safe_name[:255]

    def _generate_stored_filename(
        self,
        mime_type: str,
    ) -> str:
        extension = MIME_TYPE_EXTENSIONS[mime_type]

        return f"{uuid4().hex}{extension}"

    def _calculate_checksum(
        self,
        file_content: bytes,
    ) -> str:
        return hashlib.sha256(file_content).hexdigest()

    async def upload_document(
        self,
        course_id: int,
        user_id: int,
        uploaded_file: UploadFile,
        document_type: DocumentType = DocumentType.OTHER,
    ) -> Document:
        course = course_repository.get_course_by_id(
            db=self.db,
            course_id=course_id,
            user_id=user_id,
        )

        if course is None:
            logger.warning(
                "Document upload rejected: course not found or not owned",
                extra={
                    "course_id": course_id,
                    "user_id": user_id,
                },
            )

            raise CourseNotFoundError("Course not found.")

        mime_type = uploaded_file.content_type or ""

        self._validate_mime_type(mime_type)

        file_content = await uploaded_file.read()
        file_size = len(file_content)

        self._validate_file_size(file_size)

        original_file_name = self._sanitize_original_file_name(
            uploaded_file.filename or "uploaded-file"
        )

        checksum = self._calculate_checksum(file_content)

        duplicate = (
            self.document_repository.find_active_by_course_and_checksum(
                course_id=course_id,
                checksum=checksum,
            )
        )

        if duplicate is not None:
            logger.warning(
                "Duplicate document upload rejected",
                extra={
                    "course_id": course_id,
                    "user_id": user_id,
                    "checksum": checksum,
                    "existing_document_id": duplicate.id,
                },
            )

            raise DuplicateDocumentError(
                "The same file has already been uploaded to this course."
            )

        stored_file_name = self._generate_stored_filename(
            mime_type=mime_type,
        )

        relative_path = (
            f"courses/{course_id}/documents/{stored_file_name}"
        )

        storage_path: str | None = None

        try:
            storage_path = self.storage_service.save(
                file_content=file_content,
                relative_path=relative_path,
            )

        except (OSError, ValueError) as error:
            logger.exception(
                "Document storage failed",
                extra={
                    "course_id": course_id,
                    "user_id": user_id,
                    "original_file_name": original_file_name,
                },
            )

            raise FileStorageError(
                "The uploaded file could not be stored."
            ) from error

        document_data = {
            "course_id": course_id,
            "uploaded_by": user_id,
            "original_file_name": original_file_name,
            "stored_file_name": stored_file_name,
            "storage_path": storage_path,
            "mime_type": mime_type,
            "file_size": file_size,
            "checksum": checksum,
            "document_type": document_type,
            "processing_status": ProcessingStatus.UPLOADED,
            "processing_error": None,
        }

        try:
            document = self.document_repository.create(
                document_data=document_data,
            )

            self.db.commit()
            self.db.refresh(document)

        except SQLAlchemyError:
            self.db.rollback()

            logger.exception(
                "Document metadata persistence failed",
                extra={
                    "course_id": course_id,
                    "user_id": user_id,
                    "storage_path": storage_path,
                },
            )

            try:
                self.storage_service.delete(storage_path)

            except (OSError, ValueError):
                logger.exception(
                    "Document cleanup failed after database error",
                    extra={
                        "course_id": course_id,
                        "user_id": user_id,
                        "storage_path": storage_path,
                    },
                )

            raise

        logger.info(
            "Document upload succeeded",
            extra={
                "document_id": document.id,
                "course_id": course_id,
                "user_id": user_id,
                "original_file_name": original_file_name,
                "stored_file_name": stored_file_name,
                "mime_type": mime_type,
                "file_size": file_size,
                "checksum": checksum,
                "processing_status": document.processing_status.value,
            },
        )

        # Only enqueue after the document's own transaction has committed
        # (above) — a job must never be able to execute before the row it
        # operates on is actually visible to other connections (the worker
        # runs in a separate process/connection entirely).
        try:
            process_document.delay(document.id)

        except Exception:
            # The upload itself fully succeeded (file stored, metadata
            # persisted) — a queue-publish failure is a separate concern
            # and must not fail the request. Document stays UPLOADED
            # (an accurate, recoverable state); POST .../reprocess gives
            # an explicit retry path once Redis is reachable again.
            logger.exception(
                "Failed to enqueue document processing — document remains "
                "UPLOADED and can be retried via the reprocess endpoint",
                extra={"document_id": document.id},
            )

        else:
            document = self.document_repository.mark_queued(document)

        return document