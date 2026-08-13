from sqlalchemy.orm import Session

from app.exceptions.document import DocumentNotFoundError
from app.models.extraction_candidate import ExtractionCandidate
from app.repositories import course_repository
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_candidate_repository import (
    ExtractionCandidateRepository,
)


class ExtractionQueryService:
    """Read-only, ownership-checked listing of a document's extraction
    candidates -- mirrors DocumentQueryService's ownership-chain shape."""

    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository | None = None,
        candidate_repository: ExtractionCandidateRepository | None = None,
    ) -> None:
        self.db = db
        self.document_repository = document_repository or DocumentRepository(db)
        self.candidate_repository = (
            candidate_repository or ExtractionCandidateRepository(db)
        )

    def list_candidates(
        self, *, document_id: int, user_id: int
    ) -> list[ExtractionCandidate]:
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

        return self.candidate_repository.list_by_document(document_id)
