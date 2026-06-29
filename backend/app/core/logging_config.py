"""Structured logging setup.

Replaces the plain-text formatter with a JSON formatter (configurable back
to text for local development) and attaches the current request ID to
every log record via a logging.Filter, so log aggregation tools can
correlate every line emitted while handling a request without each
call site having to pass the ID explicitly.

Never log secrets or sensitive user data: no API keys, JWTs, passwords, or
personal user fields (email, etc.) belong in `message` or `extra`.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.request_context import get_request_id

# Attributes already present on every stdlib LogRecord — anything in
# `extra` that isn't one of these is a caller-supplied field and gets
# folded into the JSON output.
_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__.keys()
) | {"message", "asctime"}


class RequestIdFilter(logging.Filter):
    """Attach the current request ID (if any) to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Render each LogRecord as a single line of JSON."""

    converter = time.gmtime  # UTC timestamps, matching the prior formatter.

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and key != "request_id":
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(log_level: str, log_format: str) -> None:
    """Configure the root logger with the given level and output format.

    Idempotent: clears any handlers from a prior call (relevant for tests
    that re-invoke this with different settings) before installing the
    configured one.
    """
    if log_format == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(request_id)s | %(message)s"
        )
        formatter.converter = time.gmtime

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)
