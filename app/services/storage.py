from pathlib import Path


class LocalStorageService:
    def __init__(self, upload_dir: str) -> None:
        self.upload_dir = Path(upload_dir).resolve()
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        file_content: bytes,
        relative_path: str,
    ) -> str:
        target_path = (self.upload_dir / relative_path).resolve()

        if self.upload_dir not in target_path.parents:
            raise ValueError("Invalid storage path.")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(file_content)

        return str(target_path)

    def delete(
        self,
        storage_path: str,
    ) -> None:
        target_path = Path(storage_path).resolve()

        if self.upload_dir not in target_path.parents:
            raise ValueError("Invalid storage path.")

        if target_path.exists():
            target_path.unlink()