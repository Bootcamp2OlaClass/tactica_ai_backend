import asyncio
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from fastapi import UploadFile
import hashlib

from app.exceptions.document import (
    DuplicateDocumentError,
    FileStorageError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.services.document_upload import DocumentUploadService
from sqlalchemy.exc import SQLAlchemyError

from types import SimpleNamespace

from app.models.document import (
    DocumentType,
    ProcessingStatus,
)

@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def repository():
    return MagicMock()


@pytest.fixture
def storage():
    return MagicMock()


@pytest.fixture
def service(db, repository, storage):
    return DocumentUploadService(
        db=db,
        document_repository=repository,
        storage_service=storage,
    )

def test_upload_rejects_unsupported_file_type(
    service,
    repository,
    storage,
    monkeypatch,
):
    course = MagicMock(id=10)

    get_course_mock = MagicMock(return_value=course)

    monkeypatch.setattr(
        "app.services.document_upload.course_repository.get_course_by_id",
        get_course_mock,
    )

    uploaded_file = UploadFile(
        filename="notes.txt",
        file=BytesIO(b"plain text content"),
        headers={"content-type": "text/plain"},
    )

    with pytest.raises(
        UnsupportedFileTypeError,
        match="Unsupported file type",
    ):
        asyncio.run(
            service.upload_document(
                course_id=10,
                user_id=1,
                uploaded_file=uploaded_file,
            )
        )

    get_course_mock.assert_called_once_with(
        db=service.db,
        course_id=10,
        user_id=1,
    )

    repository.find_active_by_course_and_checksum.assert_not_called()
    repository.create.assert_not_called()
    storage.save.assert_not_called()
    service.db.commit.assert_not_called()

def test_upload_rejects_oversized_file(
    service,
    repository,
    storage,
    monkeypatch,
):
    course = MagicMock(id=10)

    monkeypatch.setattr(
        "app.services.document_upload.course_repository.get_course_by_id",
        MagicMock(return_value=course),
    )

    monkeypatch.setattr(
        "app.services.document_upload.settings",
        MagicMock(max_upload_size=5),
    )

    uploaded_file = UploadFile(
        filename="lecture.pdf",
        file=BytesIO(b"123456"),
        headers={"content-type": "application/pdf"},
    )

    with pytest.raises(
        FileTooLargeError,
        match="maximum allowed size",
    ):
        asyncio.run(
            service.upload_document(
                course_id=10,
                user_id=1,
                uploaded_file=uploaded_file,
            )
        )

    repository.find_active_by_course_and_checksum.assert_not_called()
    repository.create.assert_not_called()
    storage.save.assert_not_called()
    service.db.commit.assert_not_called()

def test_upload_rejects_duplicate_file(
    service,
    repository,
    storage,
    monkeypatch,
):
    course = MagicMock(id=10)
    duplicate_document = MagicMock(id=99)

    monkeypatch.setattr(
        "app.services.document_upload.course_repository.get_course_by_id",
        MagicMock(return_value=course),
    )

    repository.find_active_by_course_and_checksum.return_value = (
        duplicate_document
    )

    uploaded_file = UploadFile(
        filename="lecture.pdf",
        file=BytesIO(b"same pdf content"),
        headers={"content-type": "application/pdf"},
    )

    with pytest.raises(
        DuplicateDocumentError,
        match="already been uploaded",
    ):
        asyncio.run(
            service.upload_document(
                course_id=10,
                user_id=1,
                uploaded_file=uploaded_file,
            )
        )

    repository.find_active_by_course_and_checksum.assert_called_once()
    repository.create.assert_not_called()
    storage.save.assert_not_called()
    service.db.commit.assert_not_called()

def test_storage_failure_does_not_create_document(
    service,
    repository,
    storage,
    monkeypatch,
):
    course = MagicMock(id=10)

    monkeypatch.setattr(
        "app.services.document_upload.course_repository.get_course_by_id",
        MagicMock(return_value=course),
    )

    repository.find_active_by_course_and_checksum.return_value = None
    storage.save.side_effect = OSError("disk full")

    uploaded_file = UploadFile(
        filename="lecture.pdf",
        file=BytesIO(b"pdf content"),
        headers={"content-type": "application/pdf"},
    )

    with pytest.raises(
        FileStorageError,
        match="could not be stored",
    ):
        asyncio.run(
            service.upload_document(
                course_id=10,
                user_id=1,
                uploaded_file=uploaded_file,
            )
        )

    repository.find_active_by_course_and_checksum.assert_called_once()
    storage.save.assert_called_once()
    repository.create.assert_not_called()
    service.db.commit.assert_not_called()
    service.db.rollback.assert_not_called()
    storage.delete.assert_not_called()

def test_database_failure_cleans_up_stored_file(
    service,
    repository,
    storage,
    monkeypatch,
):
    course = MagicMock(id=10)

    monkeypatch.setattr(
        "app.services.document_upload.course_repository.get_course_by_id",
        MagicMock(return_value=course),
    )

    repository.find_active_by_course_and_checksum.return_value = None

    storage.save.return_value = (
        "/tmp/uploads/courses/10/documents/generated.pdf"
    )

    repository.create.side_effect = SQLAlchemyError(
        "database unavailable"
    )

    uploaded_file = UploadFile(
        filename="lecture.pdf",
        file=BytesIO(b"pdf content"),
        headers={"content-type": "application/pdf"},
    )

    with pytest.raises(SQLAlchemyError):
        asyncio.run(
            service.upload_document(
                course_id=10,
                user_id=1,
                uploaded_file=uploaded_file,
            )
        )

    storage.save.assert_called_once()
    repository.create.assert_called_once()
    service.db.rollback.assert_called_once()

    storage.delete.assert_called_once_with(
        "/tmp/uploads/courses/10/documents/generated.pdf"
    )

    service.db.commit.assert_not_called()

def test_upload_document_success(
    service,
    repository,
    storage,
    monkeypatch,
):
    course = MagicMock(id=10)

    monkeypatch.setattr(
        "app.services.document_upload.course_repository.get_course_by_id",
        MagicMock(return_value=course),
    )

    repository.find_active_by_course_and_checksum.return_value = None

    storage_path = (
        "/tmp/uploads/courses/10/documents/generated.pdf"
    )

    storage.save.return_value = storage_path

    created_document = SimpleNamespace(
        id=50,
        course_id=10,
        uploaded_by=1,
        processing_status=ProcessingStatus.UPLOADED,
    )

    repository.create.return_value = created_document

    uploaded_file = UploadFile(
        filename="../../lecture.pdf",
        file=BytesIO(b"pdf content"),
        headers={"content-type": "application/pdf"},
    )

    result = asyncio.run(
        service.upload_document(
            course_id=10,
            user_id=1,
            uploaded_file=uploaded_file,
            document_type=DocumentType.LECTURE_NOTE,
        )
    )

    assert result is created_document

    storage.save.assert_called_once()
    repository.create.assert_called_once()
    service.db.commit.assert_called_once()
    service.db.refresh.assert_called_once_with(
        created_document
    )
    storage.delete.assert_not_called()

    document_data = (
        repository.create.call_args.kwargs["document_data"]
    )

    assert document_data["course_id"] == 10
    assert document_data["uploaded_by"] == 1

    assert (
        document_data["original_file_name"]
        == "lecture.pdf"
    )

    assert (
        document_data["storage_path"]
        == storage_path
    )

    assert (
        document_data["mime_type"]
        == "application/pdf"
    )

    assert document_data["file_size"] == len(
        b"pdf content"
    )

    assert len(document_data["checksum"]) == 64

    assert (
        document_data["document_type"]
        is DocumentType.LECTURE_NOTE
    )

    assert (
        document_data["processing_status"]
        is ProcessingStatus.UPLOADED
    )

    assert (
        document_data["stored_file_name"]
        != "lecture.pdf"
    )

    assert document_data[
        "stored_file_name"
    ].endswith(".pdf")

def test_upload_rejects_course_not_owned_by_user(
    service,
    repository,
    storage,
    monkeypatch,
):
    get_course_mock = MagicMock(return_value=None)

    monkeypatch.setattr(
        "app.services.document_upload.course_repository.get_course_by_id",
        get_course_mock,
    )

    uploaded_file = UploadFile(
        filename="syllabus.pdf",
        file=BytesIO(b"pdf content"),
        headers={"content-type": "application/pdf"},
    )

    from app.exceptions.course import CourseNotFoundError

    with pytest.raises(
        CourseNotFoundError,
        match="Course not found",
    ):
        asyncio.run(
            service.upload_document(
                course_id=10,
                user_id=999,
                uploaded_file=uploaded_file,
                document_type=DocumentType.SYLLABUS,
            )
        )

    get_course_mock.assert_called_once_with(
        db=service.db,
        course_id=10,
        user_id=999,
    )

    repository.find_active_by_course_and_checksum.assert_not_called()
    repository.create.assert_not_called()
    storage.save.assert_not_called()
    storage.delete.assert_not_called()
    service.db.commit.assert_not_called()

def test_upload_generates_checksum_and_safe_filename(
    service,
    repository,
    storage,
    monkeypatch,
):
    course = MagicMock(id=10)

    monkeypatch.setattr(
        "app.services.document_upload.course_repository.get_course_by_id",
        MagicMock(return_value=course),
    )

    repository.find_active_by_course_and_checksum.return_value = None

    storage.save.return_value = (
        "/tmp/uploads/courses/10/documents/generated.pdf"
    )

    created_document = SimpleNamespace(
        id=1,
        processing_status=ProcessingStatus.UPLOADED,
    )

    repository.create.return_value = created_document

    content = b"hello world pdf"

    uploaded_file = UploadFile(
        filename="../../secret.pdf",
        file=BytesIO(content),
        headers={"content-type": "application/pdf"},
    )

    asyncio.run(
        service.upload_document(
            course_id=10,
            user_id=1,
            uploaded_file=uploaded_file,
        )
    )

    document_data = repository.create.call_args.kwargs["document_data"]

    expected_checksum = hashlib.sha256(content).hexdigest()

    assert document_data["checksum"] == expected_checksum

    assert document_data["original_file_name"] == "secret.pdf"

    assert document_data["stored_file_name"].endswith(".pdf")
    assert document_data["stored_file_name"] != "secret.pdf"
    assert ".." not in document_data["stored_file_name"]
    assert "/" not in document_data["stored_file_name"]