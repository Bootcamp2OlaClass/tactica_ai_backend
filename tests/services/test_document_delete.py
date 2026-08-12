from types import SimpleNamespace
from unittest.mock import Mock

import logging
from sqlalchemy.orm import Session

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.document import (
    DocumentNotFoundError,
    FileStorageError,
)
from app.services.document_delete import DocumentDeleteService


def build_service(
    *,
    document=None,
    course=None,
):
    db = Mock()
    repository = Mock()
    storage = Mock()

    repository.get_by_id.return_value = document

    service = DocumentDeleteService(
        db=db,
        document_repository=repository,
        storage_service=storage,
    )

    return service, db, repository, storage, course


def test_delete_document_success(monkeypatch):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        storage_path="/tmp/document.pdf",
        extracted_content_path=None,
        is_deleted=False,
    )
    course = SimpleNamespace(id=10)

    service, db, repository, storage, _ = build_service(
        document=document,
        course=course,
    )

    monkeypatch.setattr(
        "app.services.document_delete.course_repository.get_course_by_id",
        lambda **kwargs: course,
    )

    service.delete_document(
        document_id=1,
        user_id=100,
    )

    repository.soft_delete.assert_called_once_with(document)
    db.commit.assert_called_once()
    storage.delete.assert_called_once_with(document.storage_path)


def test_delete_document_not_found():
    service, db, repository, storage, _ = build_service(
        document=None,
    )

    with pytest.raises(DocumentNotFoundError):
        service.delete_document(
            document_id=999,
            user_id=100,
        )

    repository.soft_delete.assert_not_called()
    db.commit.assert_not_called()
    storage.delete.assert_not_called()


def test_delete_document_not_owned(monkeypatch):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        storage_path="/tmp/document.pdf",
        extracted_content_path=None,
        is_deleted=False,
    )

    service, db, repository, storage, _ = build_service(
        document=document,
    )

    monkeypatch.setattr(
        "app.services.document_delete.course_repository.get_course_by_id",
        lambda **kwargs: None,
    )

    with pytest.raises(DocumentNotFoundError):
        service.delete_document(
            document_id=1,
            user_id=999,
        )

    repository.soft_delete.assert_not_called()
    db.commit.assert_not_called()
    storage.delete.assert_not_called()


def test_delete_document_already_deleted_retries_cleanup(
    monkeypatch,
):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        storage_path="/tmp/document.pdf",
        extracted_content_path=None,
        is_deleted=True,
    )
    course = SimpleNamespace(id=10)

    service, db, repository, storage, _ = build_service(
        document=document,
        course=course,
    )

    monkeypatch.setattr(
        "app.services.document_delete.course_repository.get_course_by_id",
        lambda **kwargs: course,
    )

    service.delete_document(
        document_id=1,
        user_id=100,
    )

    repository.soft_delete.assert_not_called()
    db.commit.assert_not_called()
    storage.delete.assert_called_once_with(document.storage_path)


def test_delete_document_storage_cleanup_failure(
    monkeypatch,
):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        storage_path="/tmp/document.pdf",
        extracted_content_path=None,
        is_deleted=False,
    )
    course = SimpleNamespace(id=10)

    service, db, repository, storage, _ = build_service(
        document=document,
        course=course,
    )

    monkeypatch.setattr(
        "app.services.document_delete.course_repository.get_course_by_id",
        lambda **kwargs: course,
    )

    storage.delete.side_effect = OSError("delete failed")

    with pytest.raises(FileStorageError):
        service.delete_document(
            document_id=1,
            user_id=100,
        )

    repository.soft_delete.assert_called_once_with(document)
    db.commit.assert_called_once()
    storage.delete.assert_called_once_with(document.storage_path)


def test_delete_document_also_cleans_up_extracted_content(monkeypatch):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        storage_path="/tmp/document.pdf",
        extracted_content_path="/tmp/document.pdf.extracted.json",
        is_deleted=False,
    )
    course = SimpleNamespace(id=10)

    service, db, repository, storage, _ = build_service(
        document=document,
        course=course,
    )

    monkeypatch.setattr(
        "app.services.document_delete.course_repository.get_course_by_id",
        lambda **kwargs: course,
    )

    service.delete_document(
        document_id=1,
        user_id=100,
    )

    assert storage.delete.call_count == 2
    storage.delete.assert_any_call(document.storage_path)
    storage.delete.assert_any_call(document.extracted_content_path)


def test_delete_document_extracted_content_cleanup_failure_is_non_fatal(
    monkeypatch,
):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        storage_path="/tmp/document.pdf",
        extracted_content_path="/tmp/document.pdf.extracted.json",
        is_deleted=False,
    )
    course = SimpleNamespace(id=10)

    service, db, repository, storage, _ = build_service(
        document=document,
        course=course,
    )

    monkeypatch.setattr(
        "app.services.document_delete.course_repository.get_course_by_id",
        lambda **kwargs: course,
    )

    def delete_side_effect(path):
        if path == document.extracted_content_path:
            raise OSError("sidecar delete failed")

    storage.delete.side_effect = delete_side_effect

    # Must NOT raise -- the primary file delete already succeeded and the
    # record is already soft-deleted, so this is a non-fatal cleanup gap.
    service.delete_document(
        document_id=1,
        user_id=100,
    )

    assert storage.delete.call_count == 2


def test_delete_document_database_failure(
    monkeypatch,
):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        storage_path="/tmp/document.pdf",
        extracted_content_path=None,
        is_deleted=False,
    )
    course = SimpleNamespace(id=10)

    service, db, repository, storage, _ = build_service(
        document=document,
        course=course,
    )

    monkeypatch.setattr(
        "app.services.document_delete.course_repository.get_course_by_id",
        lambda **kwargs: course,
    )

    repository.soft_delete.side_effect = SQLAlchemyError(
        "database failure"
    )

    with pytest.raises(SQLAlchemyError):
        service.delete_document(
            document_id=1,
            user_id=100,
        )

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    storage.delete.assert_not_called()