from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_host: str
    database_port: int
    database_name: str
    database_user: str
    database_password: str = field(repr=False)
    database_url: str = field(repr=False)
    JWT_SECRET: str = field(repr=False)

    upload_dir: str
    max_upload_size: int
    cors_allowed_origins: tuple[str, ...] = field(default=())

    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    password_reset_token_expire_minutes: int = 30
    email_verification_token_expire_hours: int = 24
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15
    cookie_secure: bool = True

    storage_provider: str = "local"
    r2_account_id: str | None = field(default=None, repr=False)
    r2_access_key_id: str | None = field(default=None, repr=False)
    r2_secret_access_key: str | None = field(default=None, repr=False)
    r2_bucket_name: str | None = None
    r2_endpoint_url: str | None = None


def _required_environment_value(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ConfigurationError(f"Required environment variable {name} is not set")
    return value


def load_settings() -> Settings:
    load_dotenv()

    database_host = _required_environment_value("DATABASE_HOST").strip()
    database_name = _required_environment_value("DATABASE_NAME").strip()
    database_user = _required_environment_value("DATABASE_USER").strip()
    database_password = _required_environment_value("DATABASE_PASSWORD")
    database_url = _required_environment_value("DATABASE_URL")
    jwt_secret = _required_environment_value("JWT_SECRET")

    upload_dir = os.getenv("UPLOAD_DIR", "uploads").strip()
    max_upload_size_value = os.getenv(
        "MAX_UPLOAD_SIZE",
        str(10*1024*1024),  # Default to 10 MB
    ).strip()

    if not upload_dir:
        raise ConfigurationError("UPLOAD_DIR must not be empty")

    cors_allowed_origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:3000",
        ).split(",")
        if origin.strip()
    )

    try:
        max_upload_size = int(max_upload_size_value)
    except ValueError as exc:
        raise ConfigurationError(
            "MAX_UPLOAD_SIZE must be an integer"
        ) from exc

    if max_upload_size <= 0:
        raise ConfigurationError(
            "MAX_UPLOAD_SIZE must be greater than 0"
        )

    def _positive_int_env(name: str, default: int) -> int:
        raw_value = os.getenv(name, str(default)).strip()
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ConfigurationError(f"{name} must be an integer") from exc
        if value <= 0:
            raise ConfigurationError(f"{name} must be greater than 0")
        return value

    access_token_expire_minutes = _positive_int_env(
        "ACCESS_TOKEN_EXPIRE_MINUTES", 15
    )
    refresh_token_expire_days = _positive_int_env(
        "REFRESH_TOKEN_EXPIRE_DAYS", 30
    )
    password_reset_token_expire_minutes = _positive_int_env(
        "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", 30
    )
    email_verification_token_expire_hours = _positive_int_env(
        "EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS", 24
    )
    login_max_failed_attempts = _positive_int_env(
        "LOGIN_MAX_FAILED_ATTEMPTS", 5
    )
    login_lockout_minutes = _positive_int_env("LOGIN_LOCKOUT_MINUTES", 15)
    cookie_secure = os.getenv("COOKIE_SECURE", "true").strip().lower() not in (
        "false",
        "0",
        "no",
    )

    storage_provider = os.getenv("STORAGE_PROVIDER", "local").strip().lower()
    if storage_provider not in ("local", "r2"):
        raise ConfigurationError("STORAGE_PROVIDER must be 'local' or 'r2'")

    r2_account_id = os.getenv("R2_ACCOUNT_ID", "").strip() or None
    r2_access_key_id = os.getenv("R2_ACCESS_KEY_ID", "").strip() or None
    r2_secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip() or None
    r2_bucket_name = os.getenv("R2_BUCKET_NAME", "").strip() or None
    r2_endpoint_url = os.getenv("R2_ENDPOINT_URL", "").strip() or None

    if storage_provider == "r2" and not all(
        [r2_account_id, r2_access_key_id, r2_secret_access_key, r2_bucket_name]
    ):
        raise ConfigurationError(
            "STORAGE_PROVIDER=r2 requires R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
            "R2_SECRET_ACCESS_KEY, and R2_BUCKET_NAME"
        )

    database_port_value = _required_environment_value("DATABASE_PORT").strip()
    try:
        database_port = int(database_port_value)
    except ValueError as exc:
        raise ConfigurationError("DATABASE_PORT must be an integer") from exc

    if not 1 <= database_port <= 65535:
        raise ConfigurationError("DATABASE_PORT must be between 1 and 65535")

    try:
        parsed_url = make_url(database_url)
    except ArgumentError as exc:
        raise ConfigurationError("DATABASE_URL must be a valid SQLAlchemy URL") from exc

    if parsed_url.drivername not in {"postgresql", "postgresql+psycopg2"}:
        raise ConfigurationError(
            "DATABASE_URL must use the postgresql or postgresql+psycopg2 driver"
        )

    if not all(
        [
            parsed_url.host,
            parsed_url.database,
            parsed_url.username,
            parsed_url.password,
        ]
    ):
        raise ConfigurationError(
            "DATABASE_URL must include a host, database name, username, and password"
        )

    return Settings(
        database_host=database_host,
        database_port=database_port,
        database_name=database_name,
        database_user=database_user,
        database_password=database_password,
        database_url=database_url,
        JWT_SECRET=jwt_secret,
        upload_dir=upload_dir,
        max_upload_size=max_upload_size,
        cors_allowed_origins=cors_allowed_origins,
        access_token_expire_minutes=access_token_expire_minutes,
        refresh_token_expire_days=refresh_token_expire_days,
        password_reset_token_expire_minutes=password_reset_token_expire_minutes,
        email_verification_token_expire_hours=email_verification_token_expire_hours,
        login_max_failed_attempts=login_max_failed_attempts,
        login_lockout_minutes=login_lockout_minutes,
        cookie_secure=cookie_secure,
        storage_provider=storage_provider,
        r2_account_id=r2_account_id,
        r2_access_key_id=r2_access_key_id,
        r2_secret_access_key=r2_secret_access_key,
        r2_bucket_name=r2_bucket_name,
        r2_endpoint_url=r2_endpoint_url,
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()

settings = get_settings()