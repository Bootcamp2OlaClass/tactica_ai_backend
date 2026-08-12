from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.extraction_candidate import (
    CandidateStatus,
    CandidateType,
    ExtractionCandidate,
)


class ExtractionCandidateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        document_id: int,
        candidate_type: CandidateType,
        payload: dict,
        source_page: int | None,
    ) -> ExtractionCandidate:
        candidate = ExtractionCandidate(
            document_id=document_id,
            candidate_type=candidate_type,
            payload=payload,
            source_page=source_page,
        )
        self.db.add(candidate)
        self.db.flush()
        return candidate

    def get_by_id(self, candidate_id: int) -> ExtractionCandidate | None:
        return (
            self.db.query(ExtractionCandidate)
            .filter(ExtractionCandidate.id == candidate_id)
            .first()
        )

    def list_by_document(self, document_id: int) -> list[ExtractionCandidate]:
        return (
            self.db.query(ExtractionCandidate)
            .filter(ExtractionCandidate.document_id == document_id)
            .order_by(ExtractionCandidate.id.asc())
            .all()
        )

    def delete_pending_for_document(self, document_id: int) -> None:
        """Used when re-running extraction on a document that already has
        candidates -- clears out only still-PENDING ones so a re-run
        doesn't duplicate them, while never touching a candidate a student
        already accepted or rejected."""
        (
            self.db.query(ExtractionCandidate)
            .filter(
                ExtractionCandidate.document_id == document_id,
                ExtractionCandidate.status == CandidateStatus.PENDING,
            )
            .delete()
        )
        self.db.flush()

    def mark_accepted(
        self,
        candidate: ExtractionCandidate,
        *,
        reviewed_by: int,
        created_task_id: int | None = None,
    ) -> ExtractionCandidate:
        candidate.status = CandidateStatus.ACCEPTED
        candidate.reviewed_at = datetime.now(timezone.utc)
        candidate.reviewed_by = reviewed_by
        candidate.created_task_id = created_task_id
        self.db.commit()
        self.db.refresh(candidate)
        return candidate

    def mark_rejected(
        self,
        candidate: ExtractionCandidate,
        *,
        reviewed_by: int,
    ) -> ExtractionCandidate:
        candidate.status = CandidateStatus.REJECTED
        candidate.reviewed_at = datetime.now(timezone.utc)
        candidate.reviewed_by = reviewed_by
        self.db.commit()
        self.db.refresh(candidate)
        return candidate
