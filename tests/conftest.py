import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base

os.environ.setdefault("JWT_SECRET", "test-secret-key")

# Overridable so a locally-running, unrelated container squatting on the
# default port (a recurring reality on a shared dev machine) doesn't force
# editing this file every time — defaults to 5433, unchanged from before.
TEST_DATABASE_PORT = os.environ.get("TEST_DATABASE_PORT", "5433")
TEST_DATABASE_URL = (
    f"postgresql+psycopg2://test_user:test_password@127.0.0.1:"
    f"{TEST_DATABASE_PORT}/test_database"
)


@pytest.fixture(autouse=True)
def database_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_HOST", "127.0.0.1")
    monkeypatch.setenv("DATABASE_PORT", TEST_DATABASE_PORT)
    monkeypatch.setenv("DATABASE_NAME", "test_database")
    monkeypatch.setenv("DATABASE_USER", "test_user")
    monkeypatch.setenv("DATABASE_PASSWORD", "test_password")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
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
    engine = create_engine(
        TEST_DATABASE_URL,
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