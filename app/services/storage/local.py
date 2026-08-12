from pathlib import Path

from app.services.storage.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    """Local-disk storage — the default for dev/tests. Same behavior as the
    original LocalStorageService this replaces; only `load()` is new
    (previously `get_existing_file` returned a Path for FileResponse to
    stream directly, which doesn't generalize to a provider with no local
    filesystem, like R2)."""

    def __init__(self, upload_dir: str) -> None:
        self.upload_dir = Path(upload_dir).resolve()
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_within_upload_dir(self, relative_or_storage_path: str) -> Path:
        target_path = Path(relative_or_storage_path)
        if not target_path.is_absolute():
            target_path = self.upload_dir / target_path
        target_path = target_path.resolve()

        if self.upload_dir not in target_path.parents:
            raise ValueError("Invalid storage path.")

        return target_path

    def save(self, file_content: bytes, relative_path: str) -> str:
        target_path = self._resolve_within_upload_dir(relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(file_content)
        return str(target_path)

    def delete(self, storage_path: str) -> None:
        target_path = self._resolve_within_upload_dir(storage_path)
        if target_path.exists():
            target_path.unlink()

    def load(self, storage_path: str) -> bytes:
        target_path = self._resolve_within_upload_dir(storage_path)

        if not target_path.is_file():
            raise FileNotFoundError("Stored file does not exist.")

        return target_path.read_bytes()
