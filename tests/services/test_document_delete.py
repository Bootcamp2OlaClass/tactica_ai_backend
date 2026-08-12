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


def test_delete_document_database_failure(
    monkeypatch,
):
    document = SimpleNamespace(
        id=1,
        course_id=10,
        storage_path="/tmp/document.pdf",
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