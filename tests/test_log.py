from __future__ import annotations

import json
import logging
import os

from lapinq.log import JSONFormatter, configure_logging


def test_json_formatter_no_exc():
    fmt = JSONFormatter()
    record = logging.LogRecord("test", logging.INFO, "file.py", 1, "hello world", (), None)
    output = json.loads(fmt.format(record))
    assert output["level"] == "INFO"
    assert output["logger"] == "test"
    assert output["message"] == "hello world"
    assert "timestamp" in output
    assert "exception" not in output


def test_json_formatter_with_exc():
    fmt = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord("test", logging.ERROR, "file.py", 1, "error", (), exc_info=__import__("sys").exc_info())
    output = json.loads(fmt.format(record))
    assert output["level"] == "ERROR"
    assert output["exception"]["type"] == "ValueError"
    assert output["exception"]["value"] == "boom"
    assert "traceback" in output


def test_configure_logging_json():
    os.environ["LAGOMORPH_JSON_LOG"] = "1"
    try:
        configure_logging()
        logger = logging.getLogger("test_json")
        handler = logger.handlers[0] if logger.handlers else logging.getLogger().handlers[0]
        fmt = handler.formatter
        assert isinstance(fmt, JSONFormatter)
    finally:
        os.environ.pop("LAGOMORPH_JSON_LOG", None)


def test_configure_logging_text():
    os.environ.pop("LAGOMORPH_JSON_LOG", None)
    configure_logging()
    logger = logging.getLogger("test_text")
    handler = logger.handlers[0] if logger.handlers else logging.getLogger().handlers[0]
    assert not isinstance(handler.formatter, JSONFormatter)
