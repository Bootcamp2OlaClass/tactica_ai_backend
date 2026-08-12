import importlib
import logging
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import QueuePool

from app.core.config import ConfigurationError, get_settings, load_settings


def load_session_module():
    module_name = "app.db.session"

    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])

    return importlib.import_module(module_name)


def test_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_HOST", "database.internal")
    monkeypatch.setenv("DATABASE_PORT", "5544")
    monkeypatch.setenv("DATABASE_NAME", "tactica_test")
    monkeypatch.setenv("DATABASE_USER", "application_user")
    monkeypatch.setenv("DATABASE_PASSWORD", "environment-secret")
    monkeypatch.setenv(
        "DATABASE_URL",
        (
            "postgresql+psycopg2://application_user:"
            "environment-secret@database.internal:5544/tactica_test"
        ),
    )

    settings = load_settings()

    assert settings.database_host == "database.internal"
    assert settings.database_port == 5544
    assert settings.database_name == "tactica_test"
    assert settings.database_user == "application_user"
    assert settings.database_password == "environment-secret"
    assert settings.database_url.startswith("postgresql+psycopg2://")
    assert "environment-secret" not in repr(settings)
    assert settings.database_url not in repr(settings)


def test_settings_reject_invalid_port(monkeypatch):
    monkeypatch.setenv("DATABASE_PORT", "not-a-port")

    with pytest.raises(
        ConfigurationError,
        match="DATABASE_PORT must be an integer",
    ):
        load_settings()


def test_settings_require_all_database_values(monkeypatch):
    import app.core.config as config

    monkeypatch.delenv("DATABASE_NAME")
    monkeypatch.setattr(config, "load_dotenv", lambda: None)

    with pytest.raises(
        ConfigurationError,
        match="Required environment variable DATABASE_NAME is not set",
    ):
        load_settings()


def test_engine_uses_safe_pool_configuration():
    session_module = load_session_module()

    assert isinstance(session_module.engine.pool, QueuePool)
    assert session_module.engine.pool._pre_ping is True
    assert session_module.engine.echo is False


def test_get_db_always_closes_session(monkeypatch):
    session_module = load_session_module()
    database_session = MagicMock()

    monkeypatch.setattr(
        session_module,
        "SessionLocal",
        lambda: database_session,
    )

    dependency = session_module.get_db()

    assert next(dependency) is database_session

    dependency.close()

    database_session.close.assert_called_once_with()


def test_successful_connectivity_validation_executes_select_and_logs(
    monkeypatch,
    caplog,
):
    monkeypatch.setenv("DATABASE_HOST", "localhost")
    monkeypatch.setenv("DATABASE_PORT", "5432")
    monkeypatch.setenv("DATABASE_NAME", "test_database")
    monkeypatch.setenv("DATABASE_USER", "test_user")
    monkeypatch.setenv("DATABASE_PASSWORD", "test_password")
    monkeypatch.setenv(
        "DATABASE_URL",
        (
            "postgresql+psycopg2://test_user:"
            "test_password@localhost:5432/test_database"
        ),
    )

    get_settings.cache_clear()

    session_module = load_session_module()
    database_engine = MagicMock()
    connection = (
        database_engine.connect.return_value
        .__enter__.return_value
    )

    with caplog.at_level(
        logging.INFO,
        logger="app.db.session",
    ):
        session_module.validate_database_connection(
            database_engine=database_engine,
            database_settings=get_settings(),
        )

    executed_statement = connection.execute.call_args.args[0]

    assert str(executed_statement) == "SELECT 1"
    assert (
        "Database connection established successfully"
        in caplog.text
    )
    assert "host=localhost" in caplog.text
    assert "database=test_database" in caplog.text
    assert "test_password" not in caplog.text

    get_settings.cache_clear()


def test_failed_connectivity_validation_is_safe(
    monkeypatch,
    caplog,
):
    password = "database-password-must-not-leak"

    database_url = (
        "postgresql+psycopg2://test_user:"
        f"{password}@localhost:5432/test_database"
    )

    monkeypatch.setenv("DATABASE_PASSWORD", password)
    monkeypatch.setenv("DATABASE_URL", database_url)

    get_settings.cache_clear()

    session_module = load_session_module()
    database_engine = MagicMock()

    database_engine.connect.side_effect = OperationalError(
        "SELECT 1",
        None,
        RuntimeError(
            f"connection failed for {database_url}"
        ),
    )

    with caplog.at_level(
        logging.ERROR,
        logger="app.db.session",
    ):
        with pytest.raises(
            session_module.DatabaseConnectionError
        ) as raised:
            session_module.validate_database_connection(
                database_engine=database_engine,
                database_settings=get_settings(),
            )

    assert (
        str(raised.value)
        == "PostgreSQL database connectivity validation failed"
    )
    assert "Database connection failed" in caplog.text
    assert "reason=OperationalError" in caplog.text
    assert password not in caplog.text
    assert database_url not in caplog.text
    assert password not in str(raised.value)
    assert database_url not in str(raised.value)

    get_settings.cache_clear()


def test_health_endpoint_reports_database_and_redis_status(monkeypatch):
    import app.main as main

    main = importlib.reload(main)

    connectivity_check = MagicMock()

    monkeypatch.setattr(
        main,
        "validate_database_connection",
        connectivity_check,
    )

    redis_client = MagicMock()
    redis_client.ping.return_value = True
    monkeypatch.setattr(main.redis, "from_url", MagicMock(return_value=redis_client))

    with TestClient(main.app) as client:
        response = client.get("/health")

    connectivity_check.assert_called_once_with()
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "redis": "connected"}


def test_health_endpoint_stays_healthy_when_redis_is_unreachable(monkeypatch):
    import app.main as main

    main = importlib.reload(main)

    monkeypatch.setattr(
        main,
        "validate_database_connection",
        MagicMock(),
    )

    def _raise_connection_error(*args, **kwargs):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(main.redis, "from_url", _raise_connection_error)

    with TestClient(main.app) as client:
        response = client.get("/health")

    # Redis being down must not make the app report unhealthy or fail to
    # respond -- background-job infrastructure is optional, synchronous
    # CRUD works with no worker/Redis running at all.
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "redis": "unreachable"}
