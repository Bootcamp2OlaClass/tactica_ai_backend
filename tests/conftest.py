import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base

os.environ.setdefault("JWT_SECRET", "test-secret-key")


@pytest.fixture(autouse=True)
def database_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_HOST", "127.0.0.1")
    monkeypatch.setenv("DATABASE_PORT", "5433")
    monkeypatch.setenv("DATABASE_NAME", "test_database")
    monkeypatch.setenv("DATABASE_USER", "test_user")
    monkeypatch.setenv("DATABASE_PASSWORD", "test_password")
    monkeypatch.setenv(
        "DATABASE_URL",
        (
            "postgresql+psycopg2://"
            "test_user:test_password@127.0.0.1:5433/test_database"
        ),
    )
    monkeypatch.setenv("JWT_SECRET", "test-secret-key")
    # The test client talks over plain http://testserver — a Secure cookie
    # would never round-trip back to the client, unlike a real https deploy.
    monkeypatch.setenv("COOKIE_SECURE", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db_session():
    database_url = (
        "postgresql+psycopg2://"
        "test_user:test_password@127.0.0.1:5433/test_database"
    )

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    Base.metadata.create_all(bind=engine)

    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    session = testing_session_local()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()