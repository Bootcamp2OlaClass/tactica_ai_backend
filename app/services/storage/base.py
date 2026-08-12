from abc import ABC, abstractmethod


class StorageProvider(ABC):
    """Provider-agnostic document storage: local disk, R2, or any future backend.

    `relative_path`/`storage_path` is an opaque string as far as callers and
    the database are concerned — for `LocalStorageProvider` it becomes a
    filesystem path, for `R2StorageProvider` an object key. Nothing outside
    a provider implementation should assume which.
    """

    @abstractmethod
    def save(self, file_content: bytes, relative_path: str) -> str:
        """Persist `file_content` and return its opaque storage path/key."""

    @abstractmethod
    def delete(self, storage_path: str) -> None:
        """Delete the stored file. Must not raise if it's already gone."""

    @abstractmethod
    def load(self, storage_path: str) -> bytes:
        """Return the stored file's raw bytes.

        Raises FileNotFoundError if the file doesn't exist, ValueError for
        a storage_path a provider can't recognize as its own (e.g. path
        traversal for the local provider).
        """
