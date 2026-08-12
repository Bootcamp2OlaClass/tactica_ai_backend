"""Contract tests for StorageProvider implementations.

Run the same behavioral contract against LocalStorageProvider (real
filesystem, tmp_path) and R2StorageProvider (a fake in-memory S3-compatible
client — no real R2 bucket was available this session, so this verifies the
provider's own logic — key handling, NoSuchKey -> FileNotFoundError mapping
— without verifying actual R2 connectivity; see ADR-004 / BUGS.md).
"""

import pytest
from botocore.exceptions import ClientError

from app.services.storage.local import LocalStorageProvider
from app.services.storage.r2 import R2StorageProvider


class FakeS3Client:
    """In-memory stand-in for boto3's S3 client, just enough surface area
    for R2StorageProvider's put_object/get_object/delete_object calls."""

    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self._objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str):
        if (Bucket, Key) not in self._objects:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
                "GetObject",
            )

        class _Body:
            def __init__(self, data: bytes) -> None:
                self._data = data

            def read(self) -> bytes:
                return self._data

        return {"Body": _Body(self._objects[(Bucket, Key)])}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self._objects.pop((Bucket, Key), None)


@pytest.fixture(params=["local", "r2"])
def provider(request, tmp_path):
    if request.param == "local":
        return LocalStorageProvider(str(tmp_path))

    return R2StorageProvider(
        account_id="test-account",
        access_key_id="test-key",
        secret_access_key="test-secret",
        bucket_name="test-bucket",
        client=FakeS3Client(),
    )


def test_save_then_load_returns_the_same_bytes(provider):
    storage_path = provider.save(b"hello world", "courses/1/documents/a.pdf")

    assert provider.load(storage_path) == b"hello world"


def test_save_then_delete_then_load_raises_file_not_found(provider):
    storage_path = provider.save(b"hello world", "courses/1/documents/b.pdf")

    provider.delete(storage_path)

    with pytest.raises(FileNotFoundError):
        provider.load(storage_path)


def test_delete_of_a_nonexistent_file_does_not_raise(provider):
    # Both providers must tolerate deleting something already gone (e.g. a
    # retry after a partial failure) without raising.
    provider.delete("courses/1/documents/never-existed.pdf")


def test_load_of_a_nonexistent_file_raises_file_not_found(provider):
    with pytest.raises(FileNotFoundError):
        provider.load("courses/1/documents/never-existed.pdf")


def test_local_provider_rejects_path_traversal(tmp_path):
    provider = LocalStorageProvider(str(tmp_path))

    with pytest.raises(ValueError):
        provider.save(b"malicious", "../../etc/passwd")


def test_local_provider_rejects_traversal_on_delete_and_load(tmp_path):
    provider = LocalStorageProvider(str(tmp_path))

    with pytest.raises(ValueError):
        provider.load("../../etc/passwd")

    with pytest.raises(ValueError):
        provider.delete("../../etc/passwd")
