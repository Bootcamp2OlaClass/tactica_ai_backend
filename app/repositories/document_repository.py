from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Query, Session

from app.models.document import (
    Document,
    DocumentType,
    ExtractionMethod,
    LLMExtractionStatus,
    ProcessingStatus,
)

# Statuses from which a processing attempt may claim a document. Excludes
# PROCESSING (a genuine duplicate job must not double-claim -- see
# try_start_processing) and COMPLETED (already done, reprocessing a
# finished document isn't this phase's scope).
_CLAIMABLE_STATUSES = (
    ProcessingStatus.UPLOADED,
    ProcessingStatus.QUEUED,
    ProcessingStatus.FAILED,
)

# Same claim pattern, for the Phase 06 LLM-extraction sub-pipeline.
_CLAIMABLE_EXTRACTION_STATUSES = (
    LLMExtractionStatus.NOT_REQUESTED,
    LLMExtractionStatus.QUEUED,
    LLMExtractionStatus.FAILED,
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

    def try_start_processing(
        self,
        document_id: int,
    ) -> bool:
        """Atomically claim a document for processing.

        A single UPDATE ... WHERE statement, not a read-then-write pair --
        under Postgres's row-level locking this is genuinely race-safe: two
        concurrent workers both attempting to claim the same document will
        serialize on the row, and only one UPDATE will match the WHERE
        clause (the loser's `processing_status` is no longer in
        `_CLAIMABLE_STATUSES` by the time it runs). Returns whether *this*
        call won the claim.
        """
        result = self.db.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.is_deleted.is_(False),
                Document.processing_status.in_(_CLAIMABLE_STATUSES),
            )
            .values(
                processing_status=ProcessingStatus.PROCESSING,
                processing_error=None,
            )
        )
        self.db.commit()

        return result.rowcount == 1

    def mark_queued(
        self,
        document: Document,
    ) -> Document:
        document.processing_status = ProcessingStatus.QUEUED
        self.db.commit()
        self.db.refresh(document)

        return document

    def mark_completed(
        self,
        document: Document,
        *,
        extraction_method: ExtractionMethod,
        page_count: int,
        text_length: int,
        extracted_content_path: str,
    ) -> Document:
        document.processing_status = ProcessingStatus.COMPLETED
        document.processing_error = None
        document.processed_at = datetime.now(timezone.utc)
        document.extraction_method = extraction_method
        document.page_count = page_count
        document.text_length = text_length
        document.extracted_content_path = extracted_content_path

        self.db.commit()
        self.db.refresh(document)

        return document

    def mark_failed(
        self,
        document: Document,
        error_message: str,
        *,
        extraction_method: ExtractionMethod | None = None,
    ) -> Document:
        document.processing_status = ProcessingStatus.FAILED
        document.processing_error = error_message
        document.processed_at = datetime.now(timezone.utc)

        if extraction_method is not None:
            document.extraction_method = extraction_method

        self.db.commit()
        self.db.refresh(document)

        return document

    # --- Phase 06: LLM extraction sub-pipeline (mirrors the Phase 05
    # methods above exactly -- same atomic-claim reasoning applies) -------

    def try_start_extraction(self, document_id: int) -> bool:
        result = self.db.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.is_deleted.is_(False),
                Document.llm_extraction_status.in_(_CLAIMABLE_EXTRACTION_STATUSES),
            )
            .values(
                llm_extraction_status=LLMExtractionStatus.PROCESSING,
                llm_extraction_error=None,
            )
        )
        self.db.commit()

        return result.rowcount == 1

    def mark_extraction_queued(self, document: Document) -> Document:
        document.llm_extraction_status = LLMExtractionStatus.QUEUED
        self.db.commit()
        self.db.refresh(document)
        return document

    def mark_extraction_completed(self, document: Document) -> Document:
        document.llm_extraction_status = LLMExtractionStatus.COMPLETED
        document.llm_extraction_error = None
        self.db.commit()
        self.db.refresh(document)
        return document

    def mark_extraction_failed(self, document: Document, error_message: str) -> Document:
        document.llm_extraction_status = LLMExtractionStatus.FAILED
        document.llm_extraction_error = error_message
        self.db.commit()
        self.db.refresh(document)
        return document