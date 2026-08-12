from __future__ import annotations

import logging
import os
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIR = "logs"
DEFAULT_APP_LOG_FILE = "app.log"
DEFAULT_ERROR_LOG_FILE = "error.log"
DEFAULT_ENABLE_CONSOLE_LOG = "true"
REQUEST_ID_MISSING = "-"
TASK_ID_MISSING = "-"

request_id_var: ContextVar[str] = ContextVar("request_id", default=REQUEST_ID_MISSING)
task_id_var: ContextVar[str] = ContextVar("task_id", default=TASK_ID_MISSING)

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "access_token",
    "refresh_token",
    "token",
    "authorization",
    "jwt_secret_key",
    "database_password",
    "db_password",
    "secret",
    "api_key",
}

_REDACTED = "[REDACTED]"
_KEY_VALUE_PATTERN = re.compile(
    r"(?i)(?P<quote>[\"']?)\b(?P<key>password|password_hash|access_token|refresh_token|token|"
    r"authorization|jwt_secret_key|database_password|db_password|secret|api_key)\b(?P=quote)\s*[:=]\s*"
    r"(?P<value>"
    r"Bearer\s+[^\s,;}\]]+|"
    r"\"(?:\\.|[^\"\\])*\"|"
    r"'(?:\\.|[^'\\])*'|"
    r"[^,\s;}\]]+"
    r")"
)


def get_request_id() -> str:
    return request_id_var.get()


def set_request_id(request_id: str):
    return request_id_var.set(request_id)


def reset_request_id(token) -> None:
    request_id_var.reset(token)


def get_task_id() -> str:
    return task_id_var.get()


def set_task_id(task_id: str):
    return task_id_var.set(task_id)


def reset_task_id(token) -> None:
    task_id_var.reset(token)


def sanitize_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _REDACTED if str(key).lower() in SENSITIVE_KEYS else sanitize_sensitive_data(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [sanitize_sensitive_data(item) for item in value]

    if isinstance(value, tuple):
        return tuple(sanitize_sensitive_data(item) for item in value)

    if isinstance(value, set):
        return {sanitize_sensitive_data(item) for item in value}

    if isinstance(value, str):
        return _KEY_VALUE_PATTERN.sub(lambda match: f"{match.group('key')}={_REDACTED}", value)

    return value


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.task_id = get_task_id()
        return True


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


class UTCRequestFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        timestamp = datetime.fromtimestamp(record.created, UTC)
        return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def format(self, record: logging.LogRecord) -> str:
        record.message = sanitize_sensitive_data(record.getMessage())
        timestamp = self.formatTime(record)
        module_name = sanitize_sensitive_data(record.name)
        message = record.message

        task_id = getattr(record, "task_id", TASK_ID_MISSING)
        task_segment = f" [task_id={task_id}]" if task_id != TASK_ID_MISSING else ""

        formatted = (
            f"{timestamp} {record.levelname} [request_id={record.request_id}]"
            f"{task_segment} [module={module_name}] {message}"
        )

        if record.exc_info:
            formatted = f"{formatted}\n{sanitize_sensitive_data(self.formatException(record.exc_info))}"

        if record.stack_info:
            formatted = f"{formatted}\n{sanitize_sensitive_data(self.formatStack(record.stack_info))}"

        return formatted


def _env_bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _log_level_from_env() -> int:
    configured_level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    return getattr(logging, configured_level, logging.INFO)


def configure_logging() -> None:
    log_level = _log_level_from_env()
    log_dir = Path(os.getenv("LOG_DIR", DEFAULT_LOG_DIR))
    app_log_file = os.getenv("APP_LOG_FILE", DEFAULT_APP_LOG_FILE)
    error_log_file = os.getenv("ERROR_LOG_FILE", DEFAULT_ERROR_LOG_FILE)
    enable_console_log = _env_bool("ENABLE_CONSOLE_LOG", DEFAULT_ENABLE_CONSOLE_LOG)

    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = UTCRequestFormatter()
    request_context_filter = RequestContextFilter()

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    root_logger.setLevel(logging.DEBUG)

    app_handler = logging.FileHandler(log_dir / app_log_file)
    app_handler.setLevel(log_level)
    app_handler.addFilter(MaxLevelFilter(logging.WARNING))
    app_handler.addFilter(request_context_filter)
    app_handler.setFormatter(formatter)
    root_logger.addHandler(app_handler)

    error_handler = logging.FileHandler(log_dir / error_log_file)
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(request_context_filter)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    if enable_console_log:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.addFilter(request_context_filter)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    logging.getLogger("uvicorn.access").disabled = True
