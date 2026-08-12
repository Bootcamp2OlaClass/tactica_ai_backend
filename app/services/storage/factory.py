from app.core.config import Settings
from app.services.storage.base import StorageProvider
from app.services.storage.local import LocalStorageProvider
from app.services.storage.r2 import R2StorageProvider


def get_storage_provider(settings: Settings) -> StorageProvider:
    if settings.storage_provider == "r2":
        return R2StorageProvider(
            account_id=settings.r2_account_id,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            bucket_name=settings.r2_bucket_name,
            endpoint_url=settings.r2_endpoint_url,
        )

    return LocalStorageProvider(settings.upload_dir)
