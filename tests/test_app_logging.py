import io
import logging
import os
import sys
import unittest
from unittest.mock import patch

import app_logging


def _reset_root_logger() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.WARNING)


class ConfigureLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_root_logger()
        self.addCleanup(_reset_root_logger)

    def test_default_level_is_info(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOG_LEVEL", None)
            app_logging.configure_logging()
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_log_level_env_is_honored(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=False):
            app_logging.configure_logging()
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    def test_invalid_log_level_falls_back_to_info(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "TOTALLY_BOGUS"}, clear=False):
            app_logging.configure_logging()
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_handler_writes_to_stdout_with_expected_format(self):
        # basicConfig is a no-op if root already has handlers — start clean.
        with patch.dict(os.environ, {"LOG_LEVEL": "INFO"}, clear=False):
            app_logging.configure_logging()

        # First handler is the one we installed (basicConfig adds at most one).
        handlers = logging.getLogger().handlers
        self.assertTrue(handlers, "configure_logging() must install a handler")
        handler = handlers[0]
        self.assertIs(handler.stream, sys.stdout)

        # Confirm the format string structure by emitting a record into a buffer.
        formatter = handler.formatter
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        rendered = formatter.format(record) if formatter else ""
        # Format is "%(asctime)s - %(name)s - %(levelname)s - %(message)s".
        self.assertIn(" - test - INFO - hello", rendered)

    def test_configure_logging_does_not_swallow_subsequent_logs(self):
        buffer = io.StringIO()
        # Reset state, then replace stdout briefly so we can capture handler output.
        with patch.dict(os.environ, {"LOG_LEVEL": "INFO"}, clear=False):
            with patch.object(sys, "stdout", buffer):
                app_logging.configure_logging()
                logging.getLogger("test.module").info("payload-marker")
                for handler in logging.getLogger().handlers:
                    handler.flush()
        self.assertIn("payload-marker", buffer.getvalue())
        self.assertIn("INFO", buffer.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
