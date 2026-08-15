import os

# Must run before any `app.*` import below -- several modules (e.g.
# app/core/config.py, app/worker/tasks/roadmap.py) evaluate
# `get_settings()` once at *module import time* into a module-level
# `settings` singleton, not just inside a function. The per-test
# `database_environment` autouse fixture further down only patches
# os.environ for the duration of one test, which is too late for a
# singleton already captured during collection -- and CI never sets
# LLM_PROVIDER/*_API_KEY at all, so tests are written assuming AI is
# unconfigured unless a specific test opts in itself. A developer's local
# .env legitimately sets LLM_PROVIDER to make the *app* usable -- but
# setting these to "" (not popping/leaving them unset) is what actually
# matters: app/core/config.py calls load_dotenv() with its default
# override=False, which only skips a key already PRESENT in os.environ.
# An absent key still gets filled in from the .env file, so popping here
# would have no effect; only a present-but-empty value blocks it, and
# load_settings()'s `os.getenv(..., "").strip().lower() or None` already
# treats "" the same as unset.
os.environ["LLM_PROVIDER"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""

import pytest
from sqlalchemy import create_engine, text
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
    # CI never sets these (its workflow env: block only lists DB/Redis/JWT
    # vars), so tests are written assuming no LLM provider is configured
    # unless a specific test opts in itself (monkeypatching its own value
    # after this fixture runs). load_dotenv() in app/core/config.py reads
    # the repo's .env with override=False, so it only fills in a var that
    # isn't already set -- on a real developer machine .env legitimately
    # carries LLM_PROVIDER=<provider> so the app itself can use AI features,
    # but without this the same file leaking into `pytest` made
    # test_generate_roadmap_task's "no LLM configured" case call the real
    # Groq API instead, producing an extra (real) recommendation item and
    # failing a count assertion that CI would never see.
    monkeypatch.setenv("LLM_PROVIDER", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "")

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

    # document_chunks.embedding is a pgvector `vector` column (Phase 07) --
    # the extension must exist before create_all can create it, same as a
    # real deployment's migration does via `CREATE EXTENSION IF NOT EXISTS`.
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

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