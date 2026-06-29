import json
import logging
import time

from app.core.logging_config import JsonFormatter, configure_logging
from app.core.request_context import reset_request_id, set_request_id

# ---------------------------------------------------------------------------
# Group A — Production Logging Configuration
#
# configure_logging() runs at import time (app.main module load) using
# Settings.LOG_LEVEL / Settings.LOG_FORMAT, before any test in this session
# executes. These tests verify the resulting global logging state.
# ---------------------------------------------------------------------------


class TestLoggingConfiguration:
    def test_root_logger_level_is_info(self):
        assert logging.getLogger().getEffectiveLevel() == logging.INFO

    def test_formatter_uses_utc_timestamps(self):
        assert JsonFormatter.converter is time.gmtime

    def test_configure_logging_is_idempotent(self):
        configure_logging("INFO", "json")
        configure_logging("INFO", "json")
        assert logging.getLogger().getEffectiveLevel() == logging.INFO

    def test_configure_logging_installs_exactly_one_handler(self):
        configure_logging("INFO", "json")
        configure_logging("INFO", "json")
        assert len(logging.getLogger().handlers) == 1


class TestJsonFormatter:
    def _format(self, **extra) -> dict:
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return json.loads(JsonFormatter().format(record))

    def test_emits_valid_json_with_core_fields(self):
        payload = self._format()
        assert payload["message"] == "hello world"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "app.test"
        assert "timestamp" in payload

    def test_includes_request_id_when_present(self):
        token = set_request_id("test-request-id")
        try:
            payload = self._format(request_id="test-request-id")
        finally:
            reset_request_id(token)
        assert payload["request_id"] == "test-request-id"

    def test_omits_request_id_when_absent(self):
        payload = self._format(request_id=None)
        assert "request_id" not in payload

    def test_includes_extra_fields(self):
        payload = self._format(status_code=200, duration_ms=12.5)
        assert payload["status_code"] == 200
        assert payload["duration_ms"] == 12.5

    def test_never_logs_secret_looking_extra_as_top_level_message(self):
        # Defensive: confirm formatter output is the message text itself,
        # not a dump of the full record __dict__ (which could otherwise
        # leak attributes attached by other code).
        payload = self._format()
        assert payload["message"] == "hello world"
