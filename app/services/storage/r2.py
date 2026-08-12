import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.services.storage.base import StorageProvider


class R2StorageProvider(StorageProvider):
    """Cloudflare R2 storage (S3-compatible API) — see ADR-004.

    NOT VERIFIED against a real bucket as of Phase 03: no R2 credentials
    were available this session. Covered by contract tests against a mocked
    boto3 client instead — see tests/services/test_storage_providers.py.
    Revisit before relying on this in a real deployment.
    """

    def __init__(
        self,
        *,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        endpoint_url: str | None = None,
        client=None,
    ) -> None:
        self.bucket_name = bucket_name
        self._client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url or f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )

    def save(self, file_content: bytes, relative_path: str) -> str:
        self._client.put_object(
            Bucket=self.bucket_name,
            Key=relative_path,
            Body=file_content,
        )
        return relative_path

    def delete(self, storage_path: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket_name, Key=storage_path)
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code")
            if error_code not in ("NoSuchKey", "404"):
                raise

    def load(self, storage_path: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket_name, Key=storage_path)
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code")
            if error_code in ("NoSuchKey", "404"):
                raise FileNotFoundError("Stored file does not exist.") from error
            raise

        return response["Body"].read()
