"""Accept/reject review for extraction candidates — see ADR-006.

Only two candidate types have a real place to land when accepted, because
those are the only two the product schema currently supports as
actionable records:

- ASSIGNMENT / EXAM -> a real Task (source=DOCUMENT_EXTRACTION,
  source_document_id set for provenance).
- COURSE_INFO -> fills in Course.instructor_name/classroom, but ONLY if
  currently null — never overwrites data the student (or a prior review)
  already set. This is the "must not silently overwrite manual data"
  requirement in practice.

IMPORTANT_DATE and GRADING_POLICY have no matching column/table yet (Course
has no grading-policy field) — accepting them just records the review
decision; extending the schema to actually persist them is a real,
deliberate scope boundary for a future phase once there's a concrete
consumer (e.g. displaying policies in a course detail view), not something
to fabricate a destination for here.
"""

from datetime import datetime, time, timezone
import logging

from sqlalchemy.orm import Session

from app.exceptions.course import CourseNotFoundError
from app.exceptions.extraction import (
    ExtractionCandidateAlreadyReviewedError,
    ExtractionCandidateNotFoundError,
)
from app.models.course import Course
from app.models.extraction_candidate import (
    CandidateStatus,
    CandidateType,
    ExtractionCandidate,
)
from app.models.task import TaskSource, TaskType
from app.repositories import course_repository
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_candidate_repository import (
    ExtractionCandidateRepository,
)
from app.repositories.task_repository import create_task

logger = logging.getLogger(__name__)


class ExtractionReviewService:
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

    def _get_owned_candidate(
        self, *, candidate_id: int, user_id: int
    ) -> tuple[ExtractionCandidate, int]:
        candidate = self.candidate_repository.get_by_id(candidate_id)
        if candidate is None:
            raise ExtractionCandidateNotFoundError("Candidate not found.")

        document = self.document_repository.get_active_by_id(
            document_id=candidate.document_id
        )
        if document is None:
            raise ExtractionCandidateNotFoundError("Candidate not found.")

        course = course_repository.get_course_by_id(
            db=self.db, course_id=document.course_id, user_id=user_id
        )
        if course is None:
            raise ExtractionCandidateNotFoundError("Candidate not found.")

        return candidate, document.course_id

    def reject(self, *, candidate_id: int, user_id: int) -> ExtractionCandidate:
        candidate, _ = self._get_owned_candidate(
            candidate_id=candidate_id, user_id=user_id
        )
        if candidate.status != CandidateStatus.PENDING:
            raise ExtractionCandidateAlreadyReviewedError(
                f"Candidate already {candidate.status.value.lower()}."
            )
        return self.candidate_repository.mark_rejected(
            candidate, reviewed_by=user_id
        )

    def accept(self, *, candidate_id: int, user_id: int) -> ExtractionCandidate:
        candidate, course_id = self._get_owned_candidate(
            candidate_id=candidate_id, user_id=user_id
        )
        if candidate.status != CandidateStatus.PENDING:
            raise ExtractionCandidateAlreadyReviewedError(
                f"Candidate already {candidate.status.value.lower()}."
            )

        created_task_id = None

        if candidate.candidate_type in (CandidateType.ASSIGNMENT, CandidateType.EXAM):
            created_task_id = self._create_task_from_candidate(
                candidate, course_id=course_id
            ).id

        elif candidate.candidate_type == CandidateType.COURSE_INFO:
            self._apply_course_info(candidate, course_id=course_id)

        return self.candidate_repository.mark_accepted(
            candidate, reviewed_by=user_id, created_task_id=created_task_id
        )

    def _create_task_from_candidate(self, candidate: ExtractionCandidate, *, course_id: int):
        payload = candidate.payload
        due_at = None
        date_field = "due_date" if candidate.candidate_type == CandidateType.ASSIGNMENT else "exam_date"
        raw_date = payload.get(date_field)
        if raw_date:
            due_at = datetime.combine(
                datetime.fromisoformat(raw_date).date(), time.min, tzinfo=timezone.utc
            )

        task_type = (
            TaskType.ASSIGNMENT
            if candidate.candidate_type == CandidateType.ASSIGNMENT
            else TaskType.EXAM
        )

        task_data = {
            "course_id": course_id,
            "source_document_id": candidate.document_id,
            "title": payload.get("title", "Untitled"),
            "description": payload.get("description"),
            "task_type": task_type,
            "due_at": due_at,
            "source": TaskSource.DOCUMENT_EXTRACTION,
        }

        return create_task(self.db, task_data)

    def _apply_course_info(self, candidate: ExtractionCandidate, *, course_id: int) -> None:
        # Ownership already verified by _get_owned_candidate; fetch the
        # course row directly here since course_repository's lookup is
        # user-scoped and we've already confirmed ownership.
        course = self.db.query(Course).filter(Course.id == course_id).first()
        if course is None:
            raise CourseNotFoundError("Course not found.")

        payload = candidate.payload
        updated = False

        if not course.instructor_name and payload.get("professor_name"):
            course.instructor_name = payload["professor_name"]
            updated = True

        if not course.classroom and payload.get("classroom"):
            course.classroom = payload["classroom"]
            updated = True

        if updated:
            self.db.flush()
