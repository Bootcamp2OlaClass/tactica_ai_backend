"""Small shared helpers for building a full ownership chain
(User -> Semester -> Course -> Document) against a real db_session in
tests that need real rows, not mocks."""

from datetime import date

from app.models.course import Course, CourseStatus
from app.models.document import Document, DocumentType, ProcessingStatus
from app.models.semester import Semester, SemesterStatus
from app.models.user import User, UserRole


def create_document(
    db_session,
    *,
    processing_status: ProcessingStatus = ProcessingStatus.UPLOADED,
    storage_path: str | None = None,
    stored_file_name: str = "stored.pdf",
) -> Document:
    user = User(
        email=f"factory-{id(db_session)}-{stored_file_name}@example.com",
        password_hash="hashed-password",
        full_name="Factory Test User",
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
        stored_file_name=stored_file_name,
        storage_path=storage_path or f"/tmp/uploads/{stored_file_name}",
        mime_type="application/pdf",
        file_size=1024,
        checksum=f"checksum-{stored_file_name}",
        document_type=DocumentType.SYLLABUS,
        processing_status=processing_status,
        is_deleted=False,
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    return document


def create_document_with_owner(
    db_session,
    *,
    email_prefix: str,
    processing_status: ProcessingStatus = ProcessingStatus.COMPLETED,
    stored_file_name: str | None = None,
) -> tuple[Document, User]:
    """Same ownership chain as create_document, but also returns the owning
    User -- needed by tests that must assert on `user_id`-scoped behavior
    (Phase 07 tenant isolation) rather than just document state."""
    stored_file_name = stored_file_name or f"{email_prefix}.pdf"

    user = User(
        email=f"{email_prefix}-{id(db_session)}@example.com",
        password_hash="hashed-password",
        full_name=f"{email_prefix} Test User",
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
        stored_file_name=stored_file_name,
        storage_path=f"/tmp/uploads/{stored_file_name}",
        mime_type="application/pdf",
        file_size=1024,
        checksum=f"checksum-{stored_file_name}",
        document_type=DocumentType.SYLLABUS,
        processing_status=processing_status,
        is_deleted=False,
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    return document, user
