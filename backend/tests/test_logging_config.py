import logging
import time

from app.main import LOG_FORMAT, configure_logging

# ---------------------------------------------------------------------------
# Group A — Production Logging Configuration
#
# configure_logging() runs at import time (app.main module load), before
# any test in this session executes. These tests verify the resulting
# global logging state rather than re-driving configuration, since
# logging.basicConfig() is a no-op once the root logger already has
# handlers.
# ---------------------------------------------------------------------------


class TestLoggingConfiguration:
    def test_root_logger_level_is_info(self):
        assert logging.getLogger().getEffectiveLevel() == logging.INFO

    def test_log_format_contains_required_fields(self):
        assert "%(asctime)s" in LOG_FORMAT
        assert "%(levelname)s" in LOG_FORMAT
        assert "%(name)s" in LOG_FORMAT
        assert "%(message)s" in LOG_FORMAT

    def test_formatter_uses_utc_timestamps(self):
        assert logging.Formatter.converter is time.gmtime

    def test_configure_logging_is_idempotent(self):
        configure_logging()
        assert logging.getLogger().getEffectiveLevel() == logging.INFO
