"""Degree progress + recommendation pipeline — see PHASE_11_DEGREE_ADVISOR.md.

Every LLM recommendation passes catalog lookup -> prerequisite validation
-> requirement validation -> display, exactly as the phase brief
specifies: `_compute_eligible_courses` is the deterministic gate, and the
LLM (`recommend_next_courses`) is only ever given that already-validated
set to select from and briefly explain -- there is no free-text course
field in its output schema, only `course_code`, which is re-verified
against the exact eligible set before being trusted. There is no code
path by which the model could recommend a non-catalog course or one
whose prerequisites aren't satisfied; it can only fail to recommend
anything, never fabricate something the deterministic pass didn't
already clear.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.degree import DegreeProgramNotFoundError
from app.models.course import Course
from app.models.degree import (
    CourseCatalogEntry,
    DegreeProgram,
    DegreeRequirement,
    Prerequisite,
    StudentDegreeProgress,
)
from app.models.semester import Semester
from app.schemas.degree import DegreeRecommendationItem, DegreeRecommendations
from app.services.llm import (
    LLMExtractionError,
    LLMNotConfiguredError,
    LLMProvider,
    LLMTransientError,
    get_llm_provider,
)

logger = logging.getLogger(__name__)

MAX_RECOMMENDATIONS = 5

SYSTEM_PROMPT = """You help a university student choose which course to \
take next, from a list of courses the student is already deterministically \
eligible for (prerequisites satisfied, not yet completed, counts toward \
an unmet degree requirement) -- you are not asked to determine eligibility \
yourself, only to explain and lightly prioritize among options that are \
already valid.

Rules:
- Choose ONLY from the course_code values listed below. Never invent a \
course_code, course name, or department that isn't listed.
- Write one short, encouraging reason per course you recommend.
- If none of the eligible courses seem worth highlighting, return an \
empty list rather than forcing a recommendation.
"""


class DegreeRecommendationError(Exception):
    """Base exception for this phase's services."""


class NoDeclaredDegreeProgramError(DegreeRecommendationError):
    """Raised when the student hasn't declared a degree program yet."""


@dataclass(frozen=True)
class DegreeProgressResult:
    degree_program: DegreeProgram
    completed_course_codes: set[str]
    completed_credits: int
    unmet_requirements: list[DegreeRequirement]
    eligible_courses: list[CourseCatalogEntry] = field(default_factory=list)


class DegreeProgressService:
    """Entirely deterministic -- no LLM call anywhere in this class."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def declare_program(self, *, user_id: int, degree_program_id: int) -> DegreeProgram:
        """Idempotent: replaces any existing declaration for this student
        (one active program per student for MVP, per the model's own
        unique constraint)."""
        program = self.db.get(DegreeProgram, degree_program_id)
        if program is None:
            raise DegreeProgramNotFoundError("Degree program not found.")

        existing = (
            self.db.query(StudentDegreeProgress)
            .filter(StudentDegreeProgress.user_id == user_id)
            .first()
        )
        if existing is not None:
            existing.degree_program_id = program.id
        else:
            self.db.add(
                StudentDegreeProgress(user_id=user_id, degree_program_id=program.id)
            )
        self.db.commit()
        return program

    def compute_progress(self, user_id: int) -> DegreeProgressResult:
        declared = (
            self.db.query(StudentDegreeProgress)
            .filter(StudentDegreeProgress.user_id == user_id)
            .first()
        )
        if declared is None:
            raise NoDeclaredDegreeProgramError("No degree program declared.")

        degree_program = declared.degree_program

        completed_course_codes = {
            code
            for (code,) in self.db.query(Course.course_code)
            .join(Semester, Course.semester_id == Semester.id)
            .filter(
                Semester.user_id == user_id,
                Course.is_deleted.is_(False),
                Semester.is_deleted.is_(False),
            )
            .all()
        }

        catalog_by_code = {
            entry.course_code: entry
            for entry in self.db.query(CourseCatalogEntry)
            .filter(CourseCatalogEntry.institution_name == degree_program.institution_name)
            .all()
        }

        completed_credits = sum(
            catalog_by_code[code].credits
            for code in completed_course_codes
            if code in catalog_by_code
        )

        requirements = (
            self.db.query(DegreeRequirement)
            .filter(DegreeRequirement.degree_program_id == degree_program.id)
            .all()
        )
        unmet_requirements = [
            requirement
            for requirement in requirements
            if not self._requirement_satisfied(
                requirement, completed_course_codes, catalog_by_code
            )
        ]

        eligible_courses = self._compute_eligible_courses(
            institution_name=degree_program.institution_name,
            completed_course_codes=completed_course_codes,
            unmet_requirements=unmet_requirements,
        )

        return DegreeProgressResult(
            degree_program=degree_program,
            completed_course_codes=completed_course_codes,
            completed_credits=completed_credits,
            unmet_requirements=unmet_requirements,
            eligible_courses=eligible_courses,
        )

    def _requirement_satisfied(
        self,
        requirement: DegreeRequirement,
        completed_course_codes: set[str],
        catalog_by_code: dict[str, CourseCatalogEntry],
    ) -> bool:
        if requirement.required_course_id is not None:
            required_entry = self.db.get(CourseCatalogEntry, requirement.required_course_id)
            return required_entry is not None and required_entry.course_code in completed_course_codes

        if requirement.min_credits is not None:
            category_credits = sum(
                entry.credits
                for code, entry in catalog_by_code.items()
                if code in completed_course_codes and entry.category == requirement.category
            )
            return category_credits >= requirement.min_credits

        return True

    def _prerequisites_satisfied(
        self, catalog_entry: CourseCatalogEntry, completed_course_codes: set[str]
    ) -> bool:
        prereqs = (
            self.db.query(Prerequisite)
            .filter(Prerequisite.course_id == catalog_entry.id)
            .all()
        )
        if not prereqs:
            return True

        required_codes = {
            entry.course_code
            for entry in (
                self.db.get(CourseCatalogEntry, p.required_course_id) for p in prereqs
            )
            if entry is not None
        }
        return required_codes.issubset(completed_course_codes)

    def _compute_eligible_courses(
        self,
        *,
        institution_name: str,
        completed_course_codes: set[str],
        unmet_requirements: list[DegreeRequirement],
    ) -> list[CourseCatalogEntry]:
        """The deterministic gate every LLM recommendation must pass
        through: not yet completed, prerequisites satisfied, and counts
        toward at least one still-unmet requirement (either the exact
        required course, or shares that requirement's category)."""

        unmet_required_course_ids = {
            r.required_course_id for r in unmet_requirements if r.required_course_id is not None
        }
        unmet_categories = {
            r.category for r in unmet_requirements if r.min_credits is not None
        }

        catalog = (
            self.db.query(CourseCatalogEntry)
            .filter(CourseCatalogEntry.institution_name == institution_name)
            .all()
        )

        eligible = []
        for entry in catalog:
            if entry.course_code in completed_course_codes:
                continue
            counts_toward_requirement = (
                entry.id in unmet_required_course_ids or entry.category in unmet_categories
            )
            if not counts_toward_requirement:
                continue
            if not self._prerequisites_satisfied(entry, completed_course_codes):
                continue
            eligible.append(entry)

        return eligible


class DegreeRecommendationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        progress_service: DegreeProgressService | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.progress_service = progress_service or DegreeProgressService(db)
        self._llm_provider = llm_provider

    def _get_llm_provider(self) -> LLMProvider:
        if self._llm_provider is not None:
            return self._llm_provider
        return get_llm_provider(self.settings)

    def recommend_next_courses(
        self, *, user_id: int
    ) -> tuple[DegreeProgressResult, list[DegreeRecommendationItem], str | None]:
        """Returns (progress, recommendations, unavailable_reason).
        Raises NoDeclaredDegreeProgramError if the student hasn't
        declared a program -- that's a real precondition failure, not a
        gracefully-degradable LLM issue."""

        progress = self.progress_service.compute_progress(user_id)

        if not progress.eligible_courses:
            return progress, [], None

        try:
            provider = self._get_llm_provider()
        except LLMNotConfiguredError as exc:
            return progress, [], f"AI recommendations are not available: {exc}"

        content = self._build_content(progress)

        try:
            result = provider.extract_structured(
                system_prompt=SYSTEM_PROMPT,
                content=content,
                response_schema=DegreeRecommendations,
            )
        except (LLMTransientError, LLMExtractionError) as exc:
            logger.warning(
                "Degree recommendation generation failed, continuing "
                "without AI recommendations",
                extra={"user_id": user_id, "error": str(exc)},
            )
            return progress, [], f"AI recommendations could not be generated this time: {exc}"

        filtered = self._ground_truth_filter(result.items, progress.eligible_courses)
        return progress, filtered, None

    @staticmethod
    def _build_content(progress: DegreeProgressResult) -> str:
        lines = [
            f"- course_code={entry.course_code}: {entry.course_name} ({entry.credits} credits)"
            for entry in progress.eligible_courses
        ]
        return (
            f"Degree program: {progress.degree_program.name}\n"
            f"Completed credits: {progress.completed_credits}\n"
            f"Unmet requirements: {len(progress.unmet_requirements)}\n\n"
            "Eligible courses (already deterministically validated -- "
            "prerequisites satisfied, not yet completed, counts toward an "
            "unmet requirement):\n" + "\n".join(lines)
        )

    @staticmethod
    def _ground_truth_filter(
        items: list[DegreeRecommendationItem], eligible_courses: list[CourseCatalogEntry]
    ) -> list[DegreeRecommendationItem]:
        valid_codes = {entry.course_code for entry in eligible_courses}
        return [
            item for item in items[:MAX_RECOMMENDATIONS] if item.course_code in valid_codes
        ]
