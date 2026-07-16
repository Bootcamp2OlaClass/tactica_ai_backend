from __future__ import annotations

import logging
from collections.abc import Generator
from typing import NoReturn

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class DatabaseConnectionError(RuntimeError):
    """Raised when PostgreSQL is unavailable during startup validation."""


def get_db() -> Generator[Session, None, None]:
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()


def _raise_safe_connection_error(
    exc: SQLAlchemyError,
    database_settings: Settings,
) -> NoReturn:
    logger.error(
        "Database connection failed host=%s port=%s database=%s reason=%s",
        database_settings.database_host,
        database_settings.database_port,
        database_settings.database_name,
        type(exc).__name__,
    )
    raise DatabaseConnectionError(
        "PostgreSQL database connectivity validation failed"
    ) from None


def validate_database_connection(
    database_engine: Engine | None = None,
    database_settings: Settings | None = None,
) -> None:
    active_engine = database_engine or engine
    active_settings = database_settings or settings

    try:
        with active_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        _raise_safe_connection_error(exc, active_settings)
    except SQLAlchemyError as exc:
        _raise_safe_connection_error(exc, active_settings)

    logger.info(
        "Database connection established successfully host=%s port=%s database=%s",
        active_settings.database_host,
        active_settings.database_port,
        active_settings.database_name,
    )
