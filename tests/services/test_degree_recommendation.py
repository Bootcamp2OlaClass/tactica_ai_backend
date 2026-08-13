"""Degree advisor pipeline tests -- see PHASE_11_DEGREE_ADVISOR.md.

Uses a small synthetic catalog ("Test University", course codes like
"TEST101") -- the same test-fixture convention every other phase's tests
already use for course/task data (e.g. "CS101 Intro to CS" throughout
Phases 01-10). This is NOT a real institution's catalog and is never
presented as one; it exists solely to prove the validation pipeline
itself is correct, independent of the real-data-acquisition problem this
phase is blocked on (see PHASE_11_DEGREE_ADVISOR.md's Remaining
Limitations).

The two tests the phase brief calls out by name -- an LLM suggestion
naming a non-catalog course, or one violating a prerequisite, must be
rejected -- are test_recommend_rejects_a_non_catalog_course and
test_recommend_rejects_a_course_with_an_unmet_prerequisite below.
"""

from types import SimpleNamespace

import pytest

from app.models.course import Course, CourseStatus
from app.models.degree import CourseCatalogEntry, DegreeProgram, DegreeRequirement, Prerequisite
from app.schemas.degree import DegreeRecommendationItem, DegreeRecommendations
from app.services.degree_recommendation import (
    DegreeProgressService,
    DegreeRecommendationService,
    NoDeclaredDegreeProgramError,
)
from app.services.llm import LLMTransientError
from tests.factories import create_user_with_semester_and_course

INSTITUTION = "Test University"


class FakeLLMProvider:
    def __init__(self, result: DegreeRecommendations | None = None, error: Exception | None = None):
        self._result = result if result is not None else DegreeRecommendations(items=[])
        self._error = error

    def extract_structured(self, *, system_prompt, content, response_schema):
        if self._error is not None:
            raise self._error
        return self._result


def _build_catalog(db_session):
    entries = {}
    for code, name, credits, category in [
        ("TEST101", "Intro to Testing", 3, "CS_CORE"),
        # CS_ELECTIVE (not CS_CORE) so it counts toward the elective
        # requirement below once its own prerequisite is satisfied --
        # otherwise it would never appear as "eligible" at all, since no
        # requirement in this fixture targets a bare CS_CORE category.
        ("TEST201", "Advanced Testing", 3, "CS_ELECTIVE"),
        ("TEST301", "Testing Electives", 3, "CS_ELECTIVE"),
    ]:
        entry = CourseCatalogEntry(
            institution_name=INSTITUTION, course_code=code, course_name=name,
            credits=credits, category=category,
        )
        db_session.add(entry)
        db_session.flush()
        entries[code] = entry

    db_session.add(
        Prerequisite(course_id=entries["TEST201"].id, required_course_id=entries["TEST101"].id)
    )
    db_session.commit()
    return entries


def _build_program(db_session, entries, *, min_elective_credits=3):
    program = DegreeProgram(institution_name=INSTITUTION, name="BS Test Degree", catalog_year=2026)
    db_session.add(program)
    db_session.flush()

    db_session.add(
        DegreeRequirement(
            degree_program_id=program.id, category="core_101", required_course_id=entries["TEST101"].id
        )
    )
    db_session.add(
        DegreeRequirement(
            degree_program_id=program.id, category="CS_ELECTIVE", min_credits=min_elective_credits
        )
    )
    db_session.commit()
    db_session.refresh(program)
    return program


def _declare(db_session, user, program):
    from app.models.degree import StudentDegreeProgress

    db_session.add(StudentDegreeProgress(user_id=user.id, degree_program_id=program.id))
    db_session.commit()


def _add_completed_course(db_session, semester, *, course_code):
    course = Course(
        semester_id=semester.id, course_code=course_code, name=course_code,
        credits=3, status=CourseStatus.ACTIVE, is_deleted=False,
    )
    db_session.add(course)
    db_session.commit()
    return course


# --- DegreeProgressService (fully deterministic) ---


def test_compute_progress_raises_when_no_program_declared(db_session):
    user, semester, course = create_user_with_semester_and_course(db_session, email_prefix="degree-none")
    service = DegreeProgressService(db_session)

    with pytest.raises(NoDeclaredDegreeProgramError):
        service.compute_progress(user.id)


def test_compute_progress_counts_completed_credits_from_matching_courses(db_session):
    # create_user_with_semester_and_course's factory already adds one
    # default "CS101" course for its own chain purposes -- it matches no
    # catalog entry in this fixture (different institution's course
    # code), so it should show up in the raw completed-codes set but
    # contribute nothing to completed_credits (only catalog-matched
    # courses count toward credits). Asserted precisely below rather than
    # assuming an exact set equal to just {"TEST101"}.
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-credits")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries)
    _declare(db_session, user, program)
    _add_completed_course(db_session, semester, course_code="TEST101")

    progress = DegreeProgressService(db_session).compute_progress(user.id)

    assert "TEST101" in progress.completed_course_codes
    assert progress.completed_credits == 3


def test_specific_course_requirement_is_satisfied_once_completed(db_session):
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-req-course")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries)
    _declare(db_session, user, program)

    before = DegreeProgressService(db_session).compute_progress(user.id)
    assert any(r.category == "core_101" for r in before.unmet_requirements)

    _add_completed_course(db_session, semester, course_code="TEST101")

    after = DegreeProgressService(db_session).compute_progress(user.id)
    assert not any(r.category == "core_101" for r in after.unmet_requirements)


def test_category_requirement_is_satisfied_once_enough_credits_completed(db_session):
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-req-category")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries, min_elective_credits=3)
    _declare(db_session, user, program)

    before = DegreeProgressService(db_session).compute_progress(user.id)
    assert any(r.category == "CS_ELECTIVE" for r in before.unmet_requirements)

    _add_completed_course(db_session, semester, course_code="TEST301")

    after = DegreeProgressService(db_session).compute_progress(user.id)
    assert not any(r.category == "CS_ELECTIVE" for r in after.unmet_requirements)


def test_eligible_courses_excludes_already_completed_courses(db_session):
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-elig-completed")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries)
    _declare(db_session, user, program)
    _add_completed_course(db_session, semester, course_code="TEST101")

    progress = DegreeProgressService(db_session).compute_progress(user.id)

    assert "TEST101" not in {e.course_code for e in progress.eligible_courses}


def test_eligible_courses_excludes_courses_with_unmet_prerequisites(db_session):
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-elig-prereq")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries)
    _declare(db_session, user, program)
    # TEST101 not yet completed -> TEST201's prerequisite is unmet.

    progress = DegreeProgressService(db_session).compute_progress(user.id)

    assert "TEST201" not in {e.course_code for e in progress.eligible_courses}


def test_eligible_courses_includes_a_course_once_its_prerequisite_is_met(db_session):
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-elig-met")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries)
    _declare(db_session, user, program)
    _add_completed_course(db_session, semester, course_code="TEST101")

    progress = DegreeProgressService(db_session).compute_progress(user.id)

    assert "TEST201" in {e.course_code for e in progress.eligible_courses}


def test_eligible_courses_excludes_courses_whose_requirement_is_already_satisfied(db_session):
    """TEST301 (CS_ELECTIVE) shouldn't be surfaced as "eligible" once the
    elective requirement is already met by other means -- eligibility is
    about counting toward an *unmet* requirement, not just "a valid,
    uncompleted catalog course"."""
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-elig-satisfied")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries, min_elective_credits=3)
    _declare(db_session, user, program)
    _add_completed_course(db_session, semester, course_code="TEST301")  # satisfies the elective req directly

    progress = DegreeProgressService(db_session).compute_progress(user.id)

    # TEST301 itself is completed (excluded for that reason too), and no
    # other CS_ELECTIVE catalog entry exists in this fixture, so the
    # elective category should contribute nothing further to eligibility.
    assert not any(e.category == "CS_ELECTIVE" for e in progress.eligible_courses)


# --- DegreeRecommendationService (LLM layer + ground-truth-filter) ---


def _build_service(db_session, *, llm_provider):
    return DegreeRecommendationService(
        db=db_session, settings=SimpleNamespace(llm_provider="gemini"), llm_provider=llm_provider
    )


def test_recommend_returns_no_recommendations_when_nothing_is_eligible(db_session):
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-rec-none")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries)
    _declare(db_session, user, program)
    for code in ("TEST101", "TEST201", "TEST301"):
        _add_completed_course(db_session, semester, course_code=code)

    provider = FakeLLMProvider()
    service = _build_service(db_session, llm_provider=provider)

    progress, recommendations, reason = service.recommend_next_courses(user_id=user.id)

    assert recommendations == []
    assert reason is None


def test_recommend_returns_a_valid_recommendation_from_the_eligible_set(db_session):
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-rec-valid")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries)
    _declare(db_session, user, program)
    # TEST101 and TEST301 are both eligible (no prereqs, not completed).

    provider = FakeLLMProvider(
        DegreeRecommendations(items=[DegreeRecommendationItem(course_code="TEST101", reason="Core requirement.")])
    )
    service = _build_service(db_session, llm_provider=provider)

    progress, recommendations, reason = service.recommend_next_courses(user_id=user.id)

    assert [r.course_code for r in recommendations] == ["TEST101"]
    assert reason is None


def test_recommend_rejects_a_non_catalog_course(db_session):
    """The phase's explicit acceptance-criteria test: an LLM suggestion
    naming a course that doesn't exist in the catalog must be rejected."""
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-rec-fake-course")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries)
    _declare(db_session, user, program)

    provider = FakeLLMProvider(
        DegreeRecommendations(
            items=[DegreeRecommendationItem(course_code="MADEUP999", reason="This course does not exist.")]
        )
    )
    service = _build_service(db_session, llm_provider=provider)

    progress, recommendations, reason = service.recommend_next_courses(user_id=user.id)

    assert recommendations == []


def test_recommend_rejects_a_course_with_an_unmet_prerequisite(db_session):
    """The phase's other explicit acceptance-criteria test: an LLM
    suggestion violating a prerequisite must be rejected -- TEST201
    requires TEST101, not yet completed, so it's not in the eligible set
    even though it's a real catalog course."""
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-rec-prereq-violation")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries)
    _declare(db_session, user, program)

    provider = FakeLLMProvider(
        DegreeRecommendations(
            items=[DegreeRecommendationItem(course_code="TEST201", reason="Skip the prerequisite.")]
        )
    )
    service = _build_service(db_session, llm_provider=provider)

    progress, recommendations, reason = service.recommend_next_courses(user_id=user.id)

    assert recommendations == []


def test_recommend_handles_llm_transient_error_gracefully(db_session):
    user, semester, _ = create_user_with_semester_and_course(db_session, email_prefix="degree-rec-transient")
    entries = _build_catalog(db_session)
    program = _build_program(db_session, entries)
    _declare(db_session, user, program)

    provider = FakeLLMProvider(error=LLMTransientError("rate limited"))
    service = _build_service(db_session, llm_provider=provider)

    progress, recommendations, reason = service.recommend_next_courses(user_id=user.id)

    assert recommendations == []
    assert reason is not None
    assert progress.eligible_courses  # deterministic pass still succeeded
