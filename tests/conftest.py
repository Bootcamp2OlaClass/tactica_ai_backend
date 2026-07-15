import pytest


@pytest.fixture(autouse=True)
def database_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_HOST", "localhost")
    monkeypatch.setenv("DATABASE_PORT", "5432")
    monkeypatch.setenv("DATABASE_NAME", "test_database")
    monkeypatch.setenv("DATABASE_USER", "test_user")
    monkeypatch.setenv("DATABASE_PASSWORD", "test_password")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg2://test_user:test_password@localhost:5432/test_database",
    )

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
