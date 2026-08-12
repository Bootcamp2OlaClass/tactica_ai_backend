from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.exceptions.extraction import (
    ExtractionCandidateAlreadyReviewedError,
    ExtractionCandidateNotFoundError,
)
from app.models.extraction_candidate import CandidateStatus, CandidateType
from app.services.extraction_review import ExtractionReviewService


def build_service(*, candidate=None, document=None):
    db = MagicMock()
    document_repository = MagicMock()
    document_repository.get_active_by_id.return_value = document

    candidate_repository = MagicMock()
    candidate_repository.get_by_id.return_value = candidate
    candidate_repository.mark_accepted.side_effect = (
        lambda cand, **kwargs: SimpleNamespace(status=CandidateStatus.ACCEPTED, **kwargs)
    )
    candidate_repository.mark_rejected.side_effect = (
        lambda cand, **kwargs: SimpleNamespace(status=CandidateStatus.REJECTED, **kwargs)
    )

    service = ExtractionReviewService(
        db=db,
        document_repository=document_repository,
        candidate_repository=candidate_repository,
    )

    return service, db, document_repository, candidate_repository


def test_reject_candidate_not_found(monkeypatch):
    service, _, document_repository, candidate_repository = build_service(
        candidate=None
    )

    with pytest.raises(ExtractionCandidateNotFoundError):
        service.reject(candidate_id=1, user_id=1)


def test_reject_document_missing_is_not_found(monkeypatch):
    candidate = SimpleNamespace(id=1, document_id=5, status=CandidateStatus.PENDING)
    service, _, document_repository, candidate_repository = build_service(
        candidate=candidate, document=None
    )

    with pytest.raises(ExtractionCandidateNotFoundError):
        service.reject(candidate_id=1, user_id=1)


def test_reject_not_owned_is_not_found(monkeypatch):
    candidate = SimpleNamespace(id=1, document_id=5, status=CandidateStatus.PENDING)
    document = SimpleNamespace(id=5, course_id=10)
    service, _, document_repository, candidate_repository = build_service(
        candidate=candidate, document=document
    )
    monkeypatch.setattr(
        "app.services.extraction_review.course_repository.get_course_by_id",
        lambda **kwargs: None,
    )

    with pytest.raises(ExtractionCandidateNotFoundError):
        service.reject(candidate_id=1, user_id=999)


def test_reject_already_reviewed_raises(monkeypatch):
    candidate = SimpleNamespace(id=1, document_id=5, status=CandidateStatus.ACCEPTED)
    document = SimpleNamespace(id=5, course_id=10)
    service, _, _, candidate_repository = build_service(
        candidate=candidate, document=document
    )
    monkeypatch.setattr(
        "app.services.extraction_review.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    with pytest.raises(ExtractionCandidateAlreadyReviewedError):
        service.reject(candidate_id=1, user_id=1)

    candidate_repository.mark_rejected.assert_not_called()


def test_reject_pending_candidate_succeeds(monkeypatch):
    candidate = SimpleNamespace(id=1, document_id=5, status=CandidateStatus.PENDING)
    document = SimpleNamespace(id=5, course_id=10)
    service, _, _, candidate_repository = build_service(
        candidate=candidate, document=document
    )
    monkeypatch.setattr(
        "app.services.extraction_review.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    result = service.reject(candidate_id=1, user_id=1)

    assert result.status == CandidateStatus.REJECTED
    candidate_repository.mark_rejected.assert_called_once_with(candidate, reviewed_by=1)


def test_accept_assignment_creates_task(monkeypatch):
    candidate = SimpleNamespace(
        id=1,
        document_id=5,
        status=CandidateStatus.PENDING,
        candidate_type=CandidateType.ASSIGNMENT,
        payload={"title": "HW1", "due_date": "2026-09-01", "description": "desc"},
    )
    document = SimpleNamespace(id=5, course_id=10)
    service, db, _, candidate_repository = build_service(
        candidate=candidate, document=document
    )
    monkeypatch.setattr(
        "app.services.extraction_review.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )
    created_task = SimpleNamespace(id=99)
    create_task_mock = MagicMock(return_value=created_task)
    monkeypatch.setattr(
        "app.services.extraction_review.create_task", create_task_mock
    )

    result = service.accept(candidate_id=1, user_id=1)

    assert result.status == CandidateStatus.ACCEPTED
    create_task_mock.assert_called_once()
    task_data = create_task_mock.call_args[0][1]
    assert task_data["title"] == "HW1"
    assert task_data["course_id"] == 10
    assert task_data["source_document_id"] == 5
    candidate_repository.mark_accepted.assert_called_once_with(
        candidate, reviewed_by=1, created_task_id=99
    )


def test_accept_course_info_fills_blank_fields_only(monkeypatch):
    candidate = SimpleNamespace(
        id=1,
        document_id=5,
        status=CandidateStatus.PENDING,
        candidate_type=CandidateType.COURSE_INFO,
        payload={"professor_name": "Dr. Smith", "classroom": "204"},
    )
    document = SimpleNamespace(id=5, course_id=10)

    db = MagicMock()
    course = SimpleNamespace(id=10, instructor_name=None, classroom="Existing Room")
    db.query.return_value.filter.return_value.first.return_value = course

    document_repository = MagicMock()
    document_repository.get_active_by_id.return_value = document
    candidate_repository = MagicMock()
    candidate_repository.get_by_id.return_value = candidate
    candidate_repository.mark_accepted.side_effect = (
        lambda cand, **kwargs: SimpleNamespace(status=CandidateStatus.ACCEPTED, **kwargs)
    )

    service = ExtractionReviewService(
        db=db,
        document_repository=document_repository,
        candidate_repository=candidate_repository,
    )
    monkeypatch.setattr(
        "app.services.extraction_review.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    service.accept(candidate_id=1, user_id=1)

    assert course.instructor_name == "Dr. Smith"
    assert course.classroom == "Existing Room"  # never overwritten
    db.flush.assert_called_once()


def test_accept_already_reviewed_raises(monkeypatch):
    candidate = SimpleNamespace(
        id=1,
        document_id=5,
        status=CandidateStatus.REJECTED,
        candidate_type=CandidateType.ASSIGNMENT,
        payload={},
    )
    document = SimpleNamespace(id=5, course_id=10)
    service, _, _, candidate_repository = build_service(
        candidate=candidate, document=document
    )
    monkeypatch.setattr(
        "app.services.extraction_review.course_repository.get_course_by_id",
        lambda **kwargs: SimpleNamespace(id=10),
    )

    with pytest.raises(ExtractionCandidateAlreadyReviewedError):
        service.accept(candidate_id=1, user_id=1)

    candidate_repository.mark_accepted.assert_not_called()
