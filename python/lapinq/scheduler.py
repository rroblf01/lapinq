from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from lapinq.storage import Storage

logger = logging.getLogger("lapinq.scheduler")

SCHEDULED_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS lapinq_scheduled_tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_name   TEXT NOT NULL DEFAULT 'default',
    task_name    TEXT NOT NULL,
    module_path  TEXT NOT NULL,
    args         JSONB NOT NULL DEFAULT '[]',
    kwargs       JSONB NOT NULL DEFAULT '{}',
    cron         TEXT NOT NULL,
    ttl_seconds  DOUBLE PRECISION,
    priority     INT NOT NULL DEFAULT 0,
    max_retries  INT NOT NULL DEFAULT 3,
    metadata     JSONB DEFAULT '{}',
    retry_delay  DOUBLE PRECISION,
    retry_backoff BOOLEAN DEFAULT TRUE,
    webhook_url  TEXT,
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_triggered_at TIMESTAMPTZ
);
"""


def _parse_cron(cron: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    """Parse a cron expression into sets of minute, hour, day-of-month, month, day-of-week.

    Supports: * (all), N (specific), N-M (range), N,M (list), */N (step).
    Returns: (minutes, hours, days, months, weekdays) where all values are 0-indexed.
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression {cron!r}: expected 5 fields, got {len(parts)}")

    field_names = ["minute", "hour", "day of month", "month", "day of week"]
    field_ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]

    result: list[set[int]] = []
    for i, part in enumerate(parts):
        lo, hi = field_ranges[i]
        values: set[int] = set()
        if part == "*":
            values = set(range(lo, hi + 1))
        else:
            for segment in part.split(","):
                if "/" in segment:
                    base, step = segment.split("/")
                    step = int(step)
                    if base == "*":
                        base_range = range(lo, hi + 1)
                    elif "-" in base:
                        a, b = base.split("-")
                        base_range = range(int(a), int(b) + 1)
                    else:
                        base_range = range(int(base), hi + 1)
                    values.update(range(min(base_range), max(base_range) + 1, step))
                elif "-" in segment:
                    a, b = segment.split("-")
                    values.update(range(int(a), int(b) + 1))
                else:
                    values.add(int(segment))
        result.append(values)

    # Convert cron weekdays (0=Sun) to Python weekdays (0=Mon)
    weekdays_cron = result[4]
    weekdays_py: set[int] = set()
    for w in weekdays_cron:
        weekdays_py.add((w + 6) % 7)
    result[4] = weekdays_py

    return tuple(result)  # type: ignore[return-value]


def _should_run(cron_sets: tuple[set[int], set[int], set[int], set[int], set[int]], dt: Any) -> bool:
    """Check if a datetime matches a parsed cron expression."""
    from datetime import datetime

    minute = dt.minute
    hour = dt.hour
    day = dt.day
    month = dt.month
    weekday = dt.weekday()  # Monday=0, Sunday=6

    minutes, hours, days, months, weekdays = cron_sets
    return minute in minutes and hour in hours and day in days and month in months and weekday in weekdays


class Scheduler:
    """Periodically checks which scheduled tasks should fire and enqueues them."""

    def __init__(self, storage: Storage, interval: float = 60.0):
        self.storage = storage
        self.interval = interval
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._ensure_table()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _ensure_table(self) -> None:
        async with self.storage.pool.acquire() as conn:
            await conn.execute(SCHEDULED_TASKS_TABLE)

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(self.interval)

    async def _tick(self) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        async with self.storage.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM lapinq_scheduled_tasks WHERE enabled = TRUE"
            )
        for row in rows:
            task = dict(row)
            try:
                cron_sets = _parse_cron(task["cron"])
            except ValueError as e:
                logger.warning("Skipping scheduled task %s: %s", task.get("id"), e)
                continue
            if not _should_run(cron_sets, now):
                continue
            last = task.get("last_triggered_at")
            if last is not None and last >= now.replace(second=0, microsecond=0):
                continue
            await self.storage.enqueue(
                task_name=task["task_name"],
                queue_name=task["queue_name"],
                module_path=task["module_path"],
                args=json.loads(task.get("args", "[]")) if isinstance(task.get("args"), str) else (task.get("args") or []),
                kwargs=json.loads(task.get("kwargs", "{}")) if isinstance(task.get("kwargs"), str) else (task.get("kwargs") or {}),
                max_retries=task.get("max_retries", 3),
                priority=task.get("priority", 0),
                ttl_seconds=task.get("ttl_seconds"),
                metadata=json.loads(task.get("metadata", "{}")) if isinstance(task.get("metadata"), str) else (task.get("metadata") or {}),
                retry_delay=task.get("retry_delay"),
                retry_backoff=task.get("retry_backoff", True),
                webhook_url=task.get("webhook_url"),
            )
            logger.info(
                "Triggered scheduled task %s (%s) for queue %s",
                task["task_name"], task["cron"], task["queue_name"],
            )
            async with self.storage.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE lapinq_scheduled_tasks SET last_triggered_at = now() WHERE id = $1",
                    task["id"],
                )



