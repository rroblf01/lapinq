from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "?",
                "value": str(record.exc_info[1]),
            }
            data["traceback"] = "".join(traceback.format_exception(*record.exc_info))
        return json.dumps(data, default=str, ensure_ascii=False)


def configure_logging() -> None:
    level = os.environ.get("LAPINQ_LOG_LEVEL", "INFO").upper()
    if os.environ.get("LAPINQ_JSON_LOG", "").lower() in ("1", "true", "yes"):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logging.basicConfig(level=level, handlers=[handler], force=True)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
            force=True,
        )
