from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.exceptions.course import CourseNotFoundError
from app.exceptions.document import (
    DocumentFileMissingError,
    DocumentNotFoundError,
)
from app.models.document import DocumentType, ProcessingStatus
from app.services.document_query import DocumentQueryService


def make_document(
    *,
    document_id: int = 1,
    course_id: int = 10,
    storage_path: str = "/tmp/uploads/file.pdf",
):
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        id=document_id,
        course_id=course_id,
        uploaded_by=5,
        original_file_name="syllabus.pdf",
        stored_file_name="stored.pdf",
        storage_path=storage_path,
        mime_type="application/pdf",
        file_size=1234,
        checksum="abc123",
        document_type=DocumentType.SYLLABUS,
        processing_status=ProcessingStatus.UPLOADED,
        processing_error=None,
        created_at=now,
        updated_at=now,
        is_deleted=False,
    )


def test_list_course_documents_returns_paginated_response():
    db = MagicMock()
    repository = MagicMock()
    storage = MagicMock()
    document = make_document()

    repository.list_by_course.return_value = [document]
    repository.count_by_course.return_value = 1

    service = DocumentQueryService(
        db=db,
        document_repository=repository,
        storage_service=storage,
    )

    with patch(
        "app.services.document_query.course_repository.get_course_by_id",
        return_value=SimpleNamespace(id=10),
    ):
        result = service.list_course_documents(
            course_id=10,
            user_id=5,
            page=1,
            page_size=20,
        )

    assert result.total == 1
    assert result.total_pages == 1
    assert result.page == 1
    assert result.page_size == 20
    assert len(result.items) == 1
    assert result.items[0].original_file_name == "syllabus.pdf"

    repository.list_by_course.assert_called_once()
    repository.count_by_course.assert_called_once()


def test_list_course_documents_rejects_unowned_course():
    db = MagicMock()
    repository = MagicMock()

    service = DocumentQueryService(
        db=db,
        document_repository=repository,
        storage_service=MagicMock(),
    )

    with patch(
        "app.services.document_query.course_repository.get_course_by_id",
        return_value=None,
    ):
        with pytest.raises(CourseNotFoundError):
            service.list_course_documents(
                course_id=10,
                user_id=5,
            )

    repository.list_by_course.assert_not_called()
    repository.count_by_course.assert_not_called()


def test_get_document_returns_owned_document():
    db = MagicMock()
    repository = MagicMock()
    document = make_document()

    repository.get_active_by_id.return_value = document

    service = DocumentQueryService(
        db=db,
        document_repository=repository,
        storage_service=MagicMock(),
    )

    with patch(
        "app.services.document_query.course_repository.get_course_by_id",
        return_value=SimpleNamespace(id=10),
    ):
        result = service.get_document(
            document_id=1,
            user_id=5,
        )

    assert result is document


def test_get_document_raises_when_document_missing():
    repository = MagicMock()
    repository.get_active_by_id.return_value = None

    service = DocumentQueryService(
        db=MagicMock(),
        document_repository=repository,
        storage_service=MagicMock(),
    )

    with pytest.raises(DocumentNotFoundError):
        service.get_document(
            document_id=999,
            user_id=5,
        )


def test_get_document_hides_unowned_document():
    repository = MagicMock()
    repository.get_active_by_id.return_value = make_document()

    service = DocumentQueryService(
        db=MagicMock(),
        document_repository=repository,
        storage_service=MagicMock(),
    )

    with patch(
        "app.services.document_query.course_repository.get_course_by_id",
        return_value=None,
    ):
        with pytest.raises(DocumentNotFoundError):
            service.get_document(
                document_id=1,
                user_id=999,
            )


def test_get_document_download_returns_file_and_document():
    repository = MagicMock()
    storage = MagicMock()
    document = make_document()
    file_path = Path("/tmp/uploads/file.pdf")

    repository.get_active_by_id.return_value = document
    storage.get_existing_file.return_value = file_path

    service = DocumentQueryService(
        db=MagicMock(),
        document_repository=repository,
        storage_service=storage,
    )

    with patch(
        "app.services.document_query.course_repository.get_course_by_id",
        return_value=SimpleNamespace(id=10),
    ):
        result_path, result_document = service.get_document_download(
            document_id=1,
            user_id=5,
        )

    assert result_path == file_path
    assert result_document is document
    storage.get_existing_file.assert_called_once_with(
        document.storage_path
    )


def test_get_document_download_raises_controlled_error_when_file_missing():
    repository = MagicMock()
    storage = MagicMock()
    document = make_document()

    repository.get_active_by_id.return_value = document
    storage.get_existing_file.side_effect = FileNotFoundError

    service = DocumentQueryService(
        db=MagicMock(),
        document_repository=repository,
        storage_service=storage,
    )

    with patch(
        "app.services.document_query.course_repository.get_course_by_id",
        return_value=SimpleNamespace(id=10),
    ):
        with pytest.raises(DocumentFileMissingError):
            service.get_document_download(
                document_id=1,
                user_id=5,
            )