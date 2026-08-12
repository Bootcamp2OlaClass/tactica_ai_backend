from datetime import date, datetime, timezone

from app.models.course import Course, CourseStatus
from app.models.document import Document, DocumentType, ExtractionMethod, ProcessingStatus
from app.models.semester import Semester, SemesterStatus
from app.models.user import User, UserRole
from app.repositories.document_repository import DocumentRepository


def _make_document(db_session, *, processing_status=ProcessingStatus.UPLOADED):
    user = User(
        email="repo-test@example.com",
        password_hash="hashed-password",
        full_name="Repo Test",
        role=UserRole.STUDENT,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    semester = Semester(
        user_id=user.id,
        name="Fall 2026",
        academic_year=2026,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 15),
        status=SemesterStatus.ACTIVE,
        is_deleted=False,
    )
    db_session.add(semester)
    db_session.commit()
    db_session.refresh(semester)

    course = Course(
        semester_id=semester.id,
        course_code="CS101",
        name="Intro to CS",
        credits=3,
        status=CourseStatus.ACTIVE,
        is_deleted=False,
    )
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)

    document = Document(
        course_id=course.id,
        uploaded_by=user.id,
        original_file_name="syllabus.pdf",
        stored_file_name="stored.pdf",
        storage_path="/tmp/uploads/stored.pdf",
        mime_type="application/pdf",
        file_size=1024,
        checksum="abc123",
        document_type=DocumentType.SYLLABUS,
        processing_status=processing_status,
        is_deleted=False,
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    return document


def test_try_start_processing_claims_an_uploaded_document(db_session):
    document = _make_document(db_session, processing_status=ProcessingStatus.UPLOADED)
    repository = DocumentRepository(db_session)

    claimed = repository.try_start_processing(document.id)

    assert claimed is True
    db_session.refresh(document)
    assert document.processing_status == ProcessingStatus.PROCESSING


def test_try_start_processing_claims_a_failed_document(db_session):
    document = _make_document(db_session, processing_status=ProcessingStatus.FAILED)
    repository = DocumentRepository(db_session)

    assert repository.try_start_processing(document.id) is True


def test_try_start_processing_cannot_claim_an_already_processing_document(db_session):
    document = _make_document(db_session, processing_status=ProcessingStatus.PROCESSING)
    repository = DocumentRepository(db_session)

    claimed = repository.try_start_processing(document.id)

    assert claimed is False
    db_session.refresh(document)
    # Still PROCESSING -- unclaimed attempt must not have touched the row.
    assert document.processing_status == ProcessingStatus.PROCESSING


def test_try_start_processing_cannot_claim_a_completed_document(db_session):
    document = _make_document(db_session, processing_status=ProcessingStatus.COMPLETED)
    repository = DocumentRepository(db_session)

    assert repository.try_start_processing(document.id) is False


def test_try_start_processing_returns_false_for_a_deleted_document(db_session):
    document = _make_document(db_session, processing_status=ProcessingStatus.UPLOADED)
    document.is_deleted = True
    db_session.commit()

    repository = DocumentRepository(db_session)
    assert repository.try_start_processing(document.id) is False


def test_try_start_processing_returns_false_for_a_missing_document(db_session):
    repository = DocumentRepository(db_session)
    assert repository.try_start_processing(999999) is False


def test_mark_completed_sets_all_result_fields(db_session):
    document = _make_document(db_session, processing_status=ProcessingStatus.PROCESSING)
    repository = DocumentRepository(db_session)

    result = repository.mark_completed(
        document,
        extraction_method=ExtractionMethod.NATIVE,
        page_count=3,
        text_length=1500,
        extracted_content_path="courses/1/documents/stored.pdf.extracted.json",
    )

    assert result is document
    assert document.processing_status == ProcessingStatus.COMPLETED
    assert document.processing_error is None
    assert document.extraction_method == ExtractionMethod.NATIVE
    assert document.page_count == 3
    assert document.text_length == 1500
    assert document.extracted_content_path == "courses/1/documents/stored.pdf.extracted.json"
    assert document.processed_at is not None


def test_mark_failed_sets_error_and_clears_no_other_fields(db_session):
    document = _make_document(db_session, processing_status=ProcessingStatus.PROCESSING)
    repository = DocumentRepository(db_session)

    repository.mark_failed(document, "Unable to read this PDF.")

    assert document.processing_status == ProcessingStatus.FAILED
    assert document.processing_error == "Unable to read this PDF."
    assert document.processed_at is not None
    assert document.extraction_method is None


def test_mark_failed_can_record_extraction_method(db_session):
    document = _make_document(db_session, processing_status=ProcessingStatus.PROCESSING)
    repository = DocumentRepository(db_session)

    repository.mark_failed(
        document,
        "OCR required but unsupported.",
        extraction_method=ExtractionMethod.UNSUPPORTED,
    )

    assert document.extraction_method == ExtractionMethod.UNSUPPORTED


def test_mark_queued_transitions_status(db_session):
    document = _make_document(db_session, processing_status=ProcessingStatus.UPLOADED)
    repository = DocumentRepository(db_session)

    repository.mark_queued(document)

    assert document.processing_status == ProcessingStatus.QUEUED
