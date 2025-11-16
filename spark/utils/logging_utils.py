"""Structured logging utilities for Spark."""

from __future__ import annotations

import contextvars
import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict


_log_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    'spark_structured_log_context', default={}
)


def get_log_context() -> dict:
    """Return current structured log context."""

    return dict(_log_context.get())


@contextmanager
def structured_log_context(**fields: Any):
    """Context manager to bind structured log fields for the duration."""

    context = dict(_log_context.get())
    context.update({k: v for k, v in fields.items() if v is not None})
    token = _log_context.set(context)
    try:
        yield context
    finally:
        _log_context.reset(token)


def clear_log_context() -> None:
    """Remove all bound structured log fields."""

    _log_context.set({})


class StructuredLogger:
    """Thin wrapper that emits JSON log lines with bound context."""

    def __init__(self, name: str = 'spark.structured') -> None:
        self._logger = logging.getLogger(name)

    def debug(self, message: str, **fields: Any) -> None:
        self._log(logging.DEBUG, message, fields)

    def info(self, message: str, **fields: Any) -> None:
        self._log(logging.INFO, message, fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._log(logging.WARNING, message, fields)

    def error(self, message: str, **fields: Any) -> None:
        self._log(logging.ERROR, message, fields)

    def _log(self, level: int, message: str, extra_fields: dict) -> None:
        payload = {
            'timestamp': time.time(),
            'level': logging.getLevelName(level),
            'message': message,
            **get_log_context(),
            **extra_fields,
        }
        self._logger.log(level, _to_json(payload))


_structured_logger = StructuredLogger()


def get_structured_logger() -> StructuredLogger:
    return _structured_logger


def _to_json(payload: dict) -> str:
    def _default(obj: Any) -> Any:
        try:
            return obj.__dict__
        except Exception:
            return repr(obj)

    return json.dumps(payload, default=_default, sort_keys=True)
