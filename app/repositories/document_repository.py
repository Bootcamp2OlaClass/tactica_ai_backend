from datetime import datetime, timezone

from sqlalchemy.orm import Query, Session

from app.models.document import (
    Document,
    DocumentType,
    ProcessingStatus,
)


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_active_by_course_and_checksum(
        self,
        course_id: int,
        checksum: str,
    ) -> Document | None:
        return (
            self.db.query(Document)
            .filter(
                Document.course_id == course_id,
                Document.checksum == checksum,
                Document.is_deleted.is_(False),
            )
            .first()
        )

    def create(
        self,
        document_data: dict,
    ) -> Document:
        document = Document(**document_data)

        self.db.add(document)
        self.db.flush()

        return document

    def get_by_id(
        self,
        document_id: int,
    ) -> Document | None:
        return (
            self.db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )

    def get_active_by_id(
        self,
        document_id: int,
    ) -> Document | None:
        return (
            self.db.query(Document)
            .filter(
                Document.id == document_id,
                Document.is_deleted.is_(False),
            )
            .first()
        )

    def _apply_list_filters(
        self,
        query: Query,
        *,
        course_id: int,
        document_type: DocumentType | None = None,
        processing_status: ProcessingStatus | None = None,
        file_name_search: str | None = None,
        uploaded_from: datetime | None = None,
        uploaded_to: datetime | None = None,
    ) -> Query:
        query = query.filter(
            Document.course_id == course_id,
            Document.is_deleted.is_(False),
        )

        if document_type is not None:
            query = query.filter(
                Document.document_type == document_type,
            )

        if processing_status is not None:
            query = query.filter(
                Document.processing_status == processing_status,
            )

        if file_name_search:
            normalized_search = file_name_search.strip()

            if normalized_search:
                query = query.filter(
                    Document.original_file_name.ilike(
                        f"%{normalized_search}%"
                    )
                )

        if uploaded_from is not None:
            query = query.filter(
                Document.created_at >= uploaded_from,
            )

        if uploaded_to is not None:
            query = query.filter(
                Document.created_at <= uploaded_to,
            )

        return query

    def list_by_course(
        self,
        *,
        course_id: int,
        document_type: DocumentType | None = None,
        processing_status: ProcessingStatus | None = None,
        file_name_search: str | None = None,
        uploaded_from: datetime | None = None,
        uploaded_to: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Document]:
        query = self.db.query(Document)

        query = self._apply_list_filters(
            query,
            course_id=course_id,
            document_type=document_type,
            processing_status=processing_status,
            file_name_search=file_name_search,
            uploaded_from=uploaded_from,
            uploaded_to=uploaded_to,
        )

        return (
            query.order_by(
                Document.created_at.desc(),
                Document.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_by_course(
        self,
        *,
        course_id: int,
        document_type: DocumentType | None = None,
        processing_status: ProcessingStatus | None = None,
        file_name_search: str | None = None,
        uploaded_from: datetime | None = None,
        uploaded_to: datetime | None = None,
    ) -> int:
        query = self.db.query(Document)

        query = self._apply_list_filters(
            query,
            course_id=course_id,
            document_type=document_type,
            processing_status=processing_status,
            file_name_search=file_name_search,
            uploaded_from=uploaded_from,
            uploaded_to=uploaded_to,
        )

        return query.count()

    def soft_delete(
        self,
        document: Document,
    ) -> Document:
        if not document.is_deleted:
            document.is_deleted = True
            document.deleted_at = datetime.now(timezone.utc)
            self.db.flush()

        return document