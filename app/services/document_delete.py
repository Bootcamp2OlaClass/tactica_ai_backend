import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.exceptions.document import (
    DocumentNotFoundError,
    FileStorageError,
)
from app.repositories import course_repository
from app.repositories.document_repository import DocumentRepository
from app.services.storage import StorageProvider, get_storage_provider


logger = logging.getLogger(__name__)


class DocumentDeleteService:
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

    def delete_document(
        self,
        *,
        document_id: int,
        user_id: int,
    ) -> None:
        document = self.document_repository.get_by_id(
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
            logger.warning(
                "Document deletion rejected: document not found or not owned",
                extra={
                    "document_id": document_id,
                    "user_id": user_id,
                },
            )

            raise DocumentNotFoundError("Document not found.")

        was_already_deleted = document.is_deleted

        if not was_already_deleted:
            try:
                self.document_repository.soft_delete(document)
                self.db.commit()

            except SQLAlchemyError:
                self.db.rollback()

                logger.exception(
                    "Document soft deletion failed",
                    extra={
                        "document_id": document.id,
                        "course_id": document.course_id,
                        "user_id": user_id,
                    },
                )

                raise

        try:
            self.storage_service.delete(
                document.storage_path,
            )

        except (OSError, ValueError) as error:
            logger.exception(
                "Document physical file cleanup failed",
                extra={
                    "document_id": document.id,
                    "course_id": document.course_id,
                    "user_id": user_id,
                    "storage_path": document.storage_path,
                    "was_already_deleted": was_already_deleted,
                },
            )

            raise FileStorageError(
                "The document was marked as deleted, but its file "
                "could not be removed."
            ) from error

        logger.info(
            "Document deletion succeeded",
            extra={
                "document_id": document.id,
                "course_id": document.course_id,
                "user_id": user_id,
                "already_deleted": was_already_deleted,
            },
        )