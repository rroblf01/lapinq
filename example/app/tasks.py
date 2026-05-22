from __future__ import annotations

import logging
import time

logger = logging.getLogger("lapinq.example.tasks")


def send_email(recipient: str, subject: str, body: str) -> str:
    logger.info("Sending email to %s: %s", recipient, subject)
    time.sleep(1)
    logger.info("Email sent to %s", recipient)
    return f"sent to {recipient}: {subject}"


def add(a: int, b: int) -> int:
    return a + b


def fail() -> None:
    msg = "this task always fails"
    raise RuntimeError(msg)
