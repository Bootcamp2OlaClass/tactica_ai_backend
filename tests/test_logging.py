import asyncio
import importlib
import logging
import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response


def load_test_app(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("APP_LOG_FILE", "app.log")
    monkeypatch.setenv("ERROR_LOG_FILE", "error.log")
    monkeypatch.setenv("ENABLE_CONSOLE_LOG", "false")

    import app.core.logging as logging_config
    import app.main as main

    importlib.reload(logging_config)
    main = importlib.reload(main)
    monkeypatch.setattr(main, "validate_database_connection", lambda: True)
    return main.app


def read_logs(tmp_path):
    app_log = tmp_path / "app.log"
    error_log = tmp_path / "error.log"
    return app_log.read_text(), error_log.read_text()


def test_every_response_has_unique_request_id(monkeypatch, tmp_path):
    app = load_test_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        first_response = client.get("/health")
        second_response = client.get("/health")

    first_request_id = first_response.headers.get("X-Request-ID")
    second_request_id = second_response.headers.get("X-Request-ID")

    assert first_request_id
    assert second_request_id
    assert first_request_id != second_request_id


def test_lifecycle_logs_include_request_details(monkeypatch, tmp_path):
    app = load_test_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.get("/health")

    app_log, _ = read_logs(tmp_path)
    request_id = response.headers["X-Request-ID"]

    assert f"[request_id={request_id}]" in app_log
    assert "[module=request]" in app_log
    assert "GET /health 200" in app_log
    assert "client_ip=" in app_log
    assert re.search(r"GET /health 200 \d+ms", app_log)
    assert "Application started" in app_log
    assert "Application shutdown" in app_log


def test_log_files_are_created_and_errors_stay_out_of_app_log(monkeypatch, tmp_path):
    app = load_test_app(monkeypatch, tmp_path)

    @app.get("/boom")
    def boom():
        raise RuntimeError("password=super-secret")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    app_log, error_log = read_logs(tmp_path)

    assert (tmp_path / "app.log").exists()
    assert (tmp_path / "error.log").exists()
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "super-secret" not in response.text
    assert "ERROR" not in app_log
    assert "Traceback" in error_log
    assert "RuntimeError" in error_log
    assert error_log.count("ERROR") == 1
    assert "[module=request]" in error_log
    assert "GET /boom 500" in error_log
    assert "client_ip=" in error_log
    assert "super-secret" not in error_log
    assert "password=[REDACTED]" in error_log
    assert response.headers.get("X-Request-ID") in error_log


def test_sensitive_values_are_redacted(monkeypatch, tmp_path):
    load_test_app(monkeypatch, tmp_path)

    logging.getLogger("tests.sanitize").warning(
        'password=plain "access_token": "abc123" Authorization: Bearer token-value'
    )

    from app.core.logging import sanitize_sensitive_data

    redacted = sanitize_sensitive_data(
        {
            "password": "plain",
            "nested": [{"api_key": "key"}, {"safe": "value"}],
            "token": "token-value",
        }
    )

    app_log, _ = read_logs(tmp_path)

    assert "plain" not in app_log
    assert "abc123" not in app_log
    assert "token-value" not in app_log
    assert "[REDACTED]" in app_log
    assert redacted["password"] == "[REDACTED]"
    assert redacted["nested"][0]["api_key"] == "[REDACTED]"
    assert redacted["nested"][1]["safe"] == "value"
    assert redacted["token"] == "[REDACTED]"


def test_http_exception_behavior_remains_correct(monkeypatch, tmp_path):
    app = load_test_app(monkeypatch, tmp_path)

    @app.get("/http-error")
    def http_error():
        raise HTTPException(status_code=418, detail="teapot")

    with TestClient(app) as client:
        response = client.get("/http-error")

    assert response.status_code == 418
    assert response.json() == {"detail": "teapot"}
    assert response.headers.get("X-Request-ID")


def test_validation_error_behavior_remains_correct(monkeypatch, tmp_path):
    app = load_test_app(monkeypatch, tmp_path)

    class Payload(BaseModel):
        count: int

    @app.post("/validate")
    def validate(payload: Payload):
        return payload

    with TestClient(app) as client:
        response = client.post("/validate", json={"count": "not-an-integer"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "int_parsing"
    assert response.headers.get("X-Request-ID")


def test_configure_logging_is_idempotent(monkeypatch, tmp_path):
    load_test_app(monkeypatch, tmp_path)

    from app.core.logging import configure_logging

    configure_logging()
    configure_logging()

    file_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, logging.FileHandler)
    ]
    handler_paths = [Path(handler.baseFilename) for handler in file_handlers]

    assert handler_paths.count(tmp_path / "app.log") == 1
    assert handler_paths.count(tmp_path / "error.log") == 1

    logging.getLogger("tests.idempotent").warning("idempotent-marker")
    app_log, _ = read_logs(tmp_path)
    assert app_log.count("idempotent-marker") == 1


def test_log_levels_are_routed_to_the_correct_files(monkeypatch, tmp_path):
    load_test_app(monkeypatch, tmp_path)

    routing_logger = logging.getLogger("tests.routing")
    routing_logger.debug("debug-marker")
    routing_logger.info("info-marker")
    routing_logger.warning("warning-marker")
    routing_logger.error("error-marker")
    routing_logger.critical("critical-marker")

    app_log, error_log = read_logs(tmp_path)

    assert "debug-marker" in app_log
    assert "info-marker" in app_log
    assert "warning-marker" in app_log
    assert "error-marker" not in app_log
    assert "critical-marker" not in app_log

    assert "debug-marker" not in error_log
    assert "info-marker" not in error_log
    assert "warning-marker" not in error_log
    assert "error-marker" in error_log
    assert "critical-marker" in error_log


def test_request_context_is_reset_after_success_and_error(monkeypatch, tmp_path):
    load_test_app(monkeypatch, tmp_path)

    import app.main as main
    from app.core.logging import REQUEST_ID_MISSING, get_request_id

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/context-check",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )

    async def successful_call_next(_request):
        assert get_request_id() != REQUEST_ID_MISSING
        return Response(status_code=204)

    async def failing_call_next(_request):
        assert get_request_id() != REQUEST_ID_MISSING
        raise RuntimeError("context failure")

    successful_response = asyncio.run(
        main.request_logging_middleware(request, successful_call_next)
    )
    assert successful_response.headers.get("X-Request-ID")
    assert get_request_id() == REQUEST_ID_MISSING

    failing_response = asyncio.run(main.request_logging_middleware(request, failing_call_next))
    assert failing_response.status_code == 500
    assert failing_response.headers.get("X-Request-ID")
    assert get_request_id() == REQUEST_ID_MISSING
