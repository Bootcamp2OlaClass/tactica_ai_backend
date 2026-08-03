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
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()

settings = get_settings()